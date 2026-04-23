import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from exercises.models import Exercise


def parse_bool(raw: str, field_name: str) -> bool:
    raw = (raw or "").strip().lower()
    if raw in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "f", "no", "n", "off"}:
        return False
    if raw == "":
        return False
    raise CommandError(f"Invalid boolean for {field_name}: '{raw}'")


def normalize_choice(enum_cls, raw: str, field_name: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise CommandError(f"Missing required value for {field_name}.")

    raw_lower = raw.lower()
    for value, _label in enum_cls.choices:
        if value.lower() == raw_lower:
            return value

        # Also allow matching by the display label (case-insensitive).
        if _label.lower() == raw_lower:
            return value

    valid = ", ".join(v for v, _ in enum_cls.choices)
    raise CommandError(f"Invalid {field_name}='{raw}'. Valid values: {valid}")


def parse_secondary_muscles(raw: str) -> list[str]:
    """
    Expected CSV format:
      - semicolon-separated choice values, e.g. `chest;triceps`
      - also accepts `|` as an alternate separator
    """
    raw = (raw or "").strip()
    if not raw:
        return []

    parts = [p.strip().lower() for p in raw.replace("|", ";").split(";") if p.strip()]
    allowed = {v for v, _ in Exercise.MuscleGroup.choices}
    unknown = [p for p in parts if p not in allowed]
    if unknown:
        raise CommandError(f"Unknown secondary_muscles values: {unknown}. Allowed: {sorted(allowed)}")
    return parts


class Command(BaseCommand):
    help = "Import exercises from a CSV file into the Exercise library (safe upsert by slug or name)."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="Path to the CSV file to import.")
        parser.add_argument(
            "--mode",
            type=str,
            default="upsert",
            choices=["upsert", "skip-existing", "replace-all"],
            help=(
                "upsert=update existing (matched by slug or name) and create missing; "
                "skip-existing=create only when no slug/name match exists; "
                "replace-all=delete all exercises then import."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and print what would happen without writing to the database.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"]).expanduser().resolve()
        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")

        mode = options["mode"]
        dry_run = bool(options["dry_run"])

        if mode == "replace-all":
            if dry_run:
                self.stdout.write("Mode=replace-all --dry-run: would delete all Exercise rows.")
            else:
                self.stdout.write("Mode=replace-all: deleting existing Exercise rows...")
                Exercise.objects.all().delete()

        created = 0
        updated = 0
        skipped = 0
        total = 0
        slug_conflicts = 0

        # Columns we know how to import. Unknown columns are ignored (helps repeatability with evolving CSVs).
        known_fields = {
            "name",
            "slug",
            "category",
            "primary_muscle",
            "secondary_muscles",
            "equipment",
            "difficulty",
            "contraindications",
            "instructions",
            "active",
        }

        with csv_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise CommandError("CSV has no header row.")

            header = {h.strip() for h in reader.fieldnames if h is not None}
            missing_name = "name" not in header
            if missing_name:
                raise CommandError("CSV must include a `name` column.")

            for row_num, row in enumerate(reader, start=2):  # header is line 1
                total += 1

                name_raw = (row.get("name") or "").strip()
                if not name_raw:
                    raise CommandError(f"Row {row_num}: `name` is required.")

                slug_raw = (row.get("slug") or "").strip()
                slug_provided = bool(slug_raw)
                slug = slug_raw or slugify(name_raw)
                if not slug:
                    raise CommandError(f"Row {row_num}: could not derive a slug from `name`.")

                # Build defaults only from columns that exist in the CSV.
                defaults: dict = {"name": name_raw}

                if "category" in header and (row.get("category") or "").strip():
                    defaults["category"] = normalize_choice(Exercise.Category, row.get("category"), "category")

                if "primary_muscle" in header and (row.get("primary_muscle") or "").strip():
                    defaults["primary_muscle"] = normalize_choice(Exercise.MuscleGroup, row.get("primary_muscle"), "primary_muscle")

                if "secondary_muscles" in header:
                    # If the column exists but the value is empty, we set an empty list.
                    defaults["secondary_muscles"] = parse_secondary_muscles(row.get("secondary_muscles", ""))

                if "equipment" in header and (row.get("equipment") or "").strip():
                    defaults["equipment"] = normalize_choice(Exercise.Equipment, row.get("equipment"), "equipment")

                if "difficulty" in header and (row.get("difficulty") or "").strip():
                    defaults["difficulty"] = normalize_choice(Exercise.Difficulty, row.get("difficulty"), "difficulty")

                if "contraindications" in header:
                    defaults["contraindications"] = (row.get("contraindications") or "").strip()

                if "instructions" in header:
                    defaults["instructions"] = (row.get("instructions") or "").strip()

                if "active" in header:
                    defaults["active"] = parse_bool(row.get("active", "true"), "active")

                # Resolve duplicates:
                # 1) slug match (exact)
                # 2) name match (case-insensitive exact)
                existing = Exercise.objects.filter(slug=slug).first()
                match_type = "slug" if existing else ""

                if not existing:
                    existing = Exercise.objects.filter(name__iexact=name_raw).first()
                    match_type = "name" if existing else ""

                if dry_run:
                    if mode == "skip-existing" and existing:
                        skipped += 1
                        continue
                    if existing:
                        updated += 1
                    else:
                        created += 1
                    continue

                if existing:
                    if mode == "skip-existing":
                        skipped += 1
                        continue

                    # Avoid changing slug unless it was explicitly provided in the CSV row.
                    if slug_provided:
                        # If another record already uses this slug, that's a conflict.
                        conflict = Exercise.objects.filter(slug=slug).exclude(pk=existing.pk).exists()
                        if conflict:
                            slug_conflicts += 1
                        else:
                            existing.slug = slug

                    for field, value in defaults.items():
                        setattr(existing, field, value)

                    existing.save()
                    updated += 1
                else:
                    if mode == "skip-existing":
                        skipped += 1
                        continue

                    # Create using slug (generated or provided).
                    if mode == "replace-all":
                        # Since we deleted everything, there shouldn't be any existing rows,
                        # but we still call update_or_create to be resilient to duplicate rows in the same CSV.
                        obj, was_created = Exercise.objects.update_or_create(slug=slug, defaults=defaults)
                        if was_created:
                            created += 1
                        else:
                            updated += 1
                    else:
                        Exercise.objects.create(slug=slug, **defaults)
                        created += 1

        # Pretty output summary.
        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry-run complete. Processed {total} rows."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Import complete. Processed {total} rows."))

        self.stdout.write(f"Created: {created}")
        self.stdout.write(f"Updated: {updated}")
        self.stdout.write(f"Skipped: {skipped}")
        if slug_conflicts:
            self.stdout.write(self.style.WARNING(f"Slug conflicts (slug provided but not applied): {slug_conflicts}"))

