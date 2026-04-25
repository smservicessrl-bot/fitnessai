from django.core.management.base import BaseCommand
from django.db import transaction

from exercises.models import Exercise
from members.models import GymEquipment


BASIC_EQUIPMENT = [
    "Rúd",
    "Súlyzó",
    "Kettlebell",
    "Kábel",
    "Mellgép",
    "Lábtoló gép",
    "Evezőpad",
    "Futópad",
    "Szobakerékpár",
    "Ellenállási szalag",
    "Matrac",
]


BASIC_EXERCISES = [
    {
        "name": "Guggolás rúddal",
        "slug": "guggolas-ruddal",
        "category": Exercise.Category.STRENGTH,
        "primary_muscle": Exercise.MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes", "core"],
        "equipment": Exercise.Equipment.BARBELL,
        "difficulty": Exercise.Difficulty.INTERMEDIATE,
        "contraindications": "Térdfájdalom esetén csökkentsd a mélységet és a terhelést.",
        "instructions": "Vállszéles terpesz, feszes törzs, kontrollált leengedés, erőteljes felállás.",
        "active": True,
    },
    {
        "name": "Fekvenyomás rúddal",
        "slug": "fekvenyomas-ruddal",
        "category": Exercise.Category.STRENGTH,
        "primary_muscle": Exercise.MuscleGroup.CHEST,
        "secondary_muscles": ["triceps", "shoulders"],
        "equipment": Exercise.Equipment.BARBELL,
        "difficulty": Exercise.Difficulty.INTERMEDIATE,
        "contraindications": "Váll impingement esetén csökkentsd a mozgástartományt.",
        "instructions": "Lapockazárás, stabil lábtámasz, rúd kontrollált leengedése mellkasra.",
        "active": True,
    },
    {
        "name": "Evezés döntött törzzsel",
        "slug": "evezes-dontott-torzsel",
        "category": Exercise.Category.HYPERTROPHY,
        "primary_muscle": Exercise.MuscleGroup.BACK,
        "secondary_muscles": ["biceps", "core"],
        "equipment": Exercise.Equipment.BARBELL,
        "difficulty": Exercise.Difficulty.INTERMEDIATE,
        "contraindications": "Derékfájás esetén válts mellkassal megtámasztott evezésre.",
        "instructions": "Semleges gerinc, könyök hátrahúzása, lapockák közelítése a felső ponton.",
        "active": True,
    },
    {
        "name": "Kitörés súlyzóval",
        "slug": "kitores-sulyzoval",
        "category": Exercise.Category.HYPERTROPHY,
        "primary_muscle": Exercise.MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes", "hamstrings"],
        "equipment": Exercise.Equipment.DUMBBELL,
        "difficulty": Exercise.Difficulty.BEGINNER,
        "contraindications": "Térd instabilitásnál rövidebb lépéshosszal végezd.",
        "instructions": "Egyenes törzs, elöl lévő sarok terhelése, kontrollált visszalépés.",
        "active": True,
    },
    {
        "name": "Román felhúzás súlyzóval",
        "slug": "roman-felhuzas-sulyzoval",
        "category": Exercise.Category.STRENGTH,
        "primary_muscle": Exercise.MuscleGroup.HAMSTRINGS,
        "secondary_muscles": ["glutes", "back"],
        "equipment": Exercise.Equipment.DUMBBELL,
        "difficulty": Exercise.Difficulty.INTERMEDIATE,
        "contraindications": "Deréktáji panasz esetén kisebb súlyt és rövidebb mozgástartományt használj.",
        "instructions": "Csípőből döntés, enyhén hajlított térd, súly közel a combhoz.",
        "active": True,
    },
    {
        "name": "Vállból nyomás ülve",
        "slug": "vallbol-nyomas-ulve",
        "category": Exercise.Category.STRENGTH,
        "primary_muscle": Exercise.MuscleGroup.SHOULDERS,
        "secondary_muscles": ["triceps", "core"],
        "equipment": Exercise.Equipment.DUMBBELL,
        "difficulty": Exercise.Difficulty.BEGINNER,
        "contraindications": "Vállfájdalom esetén válassz semleges fogást és kisebb súlyt.",
        "instructions": "Stabil ülés, könyök a csukló alatt, nyomás fej fölé kontrolláltan.",
        "active": True,
    },
    {
        "name": "Plank",
        "slug": "plank",
        "category": Exercise.Category.CORE,
        "primary_muscle": Exercise.MuscleGroup.CORE,
        "secondary_muscles": ["shoulders", "glutes"],
        "equipment": Exercise.Equipment.BODYWEIGHT,
        "difficulty": Exercise.Difficulty.BEGINNER,
        "contraindications": "Derékfájás esetén rövidebb ideig tartsd és figyelj a medencehelyzetre.",
        "instructions": "Egyenes testtartás, hasfeszítés, könyök váll alatt, egyenletes légzés.",
        "active": True,
    },
    {
        "name": "Csípőemelés talajon",
        "slug": "csipoemeles-talajon",
        "category": Exercise.Category.CORE,
        "primary_muscle": Exercise.MuscleGroup.GLUTES,
        "secondary_muscles": ["hamstrings", "core"],
        "equipment": Exercise.Equipment.BODYWEIGHT,
        "difficulty": Exercise.Difficulty.BEGINNER,
        "contraindications": "Csípőtáji fájdalom esetén csökkentsd a mozgástartományt.",
        "instructions": "Sarokból nyomj, medence billentésével emeld a csípőt, fent rövid megtartás.",
        "active": True,
    },
    {
        "name": "Húzódzkodás gumiszalaggal",
        "slug": "huzodzkodas-gumiszalaggal",
        "category": Exercise.Category.STRENGTH,
        "primary_muscle": Exercise.MuscleGroup.BACK,
        "secondary_muscles": ["biceps", "core"],
        "equipment": Exercise.Equipment.BAND,
        "difficulty": Exercise.Difficulty.INTERMEDIATE,
        "contraindications": "Könyökfájdalom esetén semleges fogással végezd.",
        "instructions": "Mellkas nyitva, váll leszorítva, húzd magad a rúd felé kontrolláltan.",
        "active": True,
    },
    {
        "name": "Kettlebell lendítés",
        "slug": "kettlebell-lendites",
        "category": Exercise.Category.CARDIO,
        "primary_muscle": Exercise.MuscleGroup.GLUTES,
        "secondary_muscles": ["hamstrings", "core"],
        "equipment": Exercise.Equipment.KETTLEBELL,
        "difficulty": Exercise.Difficulty.INTERMEDIATE,
        "contraindications": "Deréksérülés esetén csak edzői felügyelettel végezd.",
        "instructions": "Csípődomináns mozgás, semleges gerinc, kar csak vezet, nem emel.",
        "active": True,
    },
    {
        "name": "Mellről tolás gépen",
        "slug": "mellrol-tolas-gepen",
        "category": Exercise.Category.HYPERTROPHY,
        "primary_muscle": Exercise.MuscleGroup.CHEST,
        "secondary_muscles": ["triceps", "shoulders"],
        "equipment": Exercise.Equipment.MACHINE,
        "difficulty": Exercise.Difficulty.BEGINNER,
        "contraindications": "Vállérzékenység esetén állítsd be alacsonyabb mozgáspályára.",
        "instructions": "Állítsd be az ülést, stabil törzs, kontrollált tolás és visszaengedés.",
        "active": True,
    },
    {
        "name": "Evezés kábelgépen",
        "slug": "evezes-kabelgepen",
        "category": Exercise.Category.HYPERTROPHY,
        "primary_muscle": Exercise.MuscleGroup.BACK,
        "secondary_muscles": ["biceps", "shoulders"],
        "equipment": Exercise.Equipment.CABLE,
        "difficulty": Exercise.Difficulty.BEGINNER,
        "contraindications": "Derékpanasz esetén használj háttámaszt vagy csökkentsd a súlyt.",
        "instructions": "Egyenes törzs, lapockazárás a végpontban, lassú visszaengedés.",
        "active": True,
    },
]


class Command(BaseCommand):
    help = "Seed Hungarian basic default content (gym equipment + exercises)."

    @transaction.atomic
    def handle(self, *args, **options):
        created_equipment = 0
        created_exercises = 0
        updated_exercises = 0

        for equipment_name in BASIC_EQUIPMENT:
            _obj, was_created = GymEquipment.objects.get_or_create(equipment=equipment_name)
            if was_created:
                created_equipment += 1

        for exercise_data in BASIC_EXERCISES:
            slug = exercise_data["slug"]
            defaults = {k: v for k, v in exercise_data.items() if k != "slug"}
            _exercise, was_created = Exercise.objects.update_or_create(slug=slug, defaults=defaults)
            if was_created:
                created_exercises += 1
            else:
                updated_exercises += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Basic Hungarian seed completed. "
                f"Equipment created: {created_equipment}. "
                f"Exercises created: {created_exercises}. "
                f"Exercises updated: {updated_exercises}."
            )
        )
