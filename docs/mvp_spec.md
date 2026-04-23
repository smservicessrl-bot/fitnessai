# FitnessAI MVP Spec: One-Day Gym Workout Planner (Django)

## 1. Product Goal
Build a tablet-friendly Django app that lets a trainer or gym staff member generate a personalized **one-day workout plan** for a gym member.

The plan generator must follow **structured business logic** (rule-based constraints, exercise selection rules, progression rules, safety checks). AI may assist, but it should only propose options within the allowed structure.

The system must also **store workout history** and **collect feedback** so future plan generation can improve over time.

Non-goals for MVP: no voice, no payments, no nutrition features, no mobile app, and no autonomous AI-driven planning without guardrails.

## 2. User Roles
1. **Gym Staff / Trainer (Authenticated)**
   - Creates workout plans for members.
   - Reviews the generated plan for safety and suitability.
   - Can make manual edits before the member starts the workout (MVP assumes edits are minimal but should be supported).
   - Starts/records workout sessions and adds staff notes when needed.
2. **Gym Member (Authenticated, limited actions)**
   - Can complete a workout session (or confirm completion) and record light feedback (e.g., pain level, RPE, notes).
   - Can view their own past plans and history (read-only for MVP).
3. **Admin (Django admin)**
   - Manages exercise library, equipment catalog, and training templates/rules.
   - Monitors data quality and review queues (if any).

## 3. Core Gym Workflow
1. Trainer selects a member on the tablet.
2. Trainer enters **session inputs** (time available, equipment present, focus, pain/injury notes, etc.).
3. Backend generates a **one-day workout plan**:
   - Uses the member profile and workout history.
   - Applies safety constraints and structured progression logic.
   - Optionally uses AI to select/justify exercise substitutions, but always within allowed exercise candidates and rule limits.
4. Trainer reviews the plan on the tablet and can:
   - Accept as-is.
   - Apply small adjustments (e.g., swap an exercise from the suggested alternatives, adjust reps for pain, or edit notes).
5. Member performs the workout.
6. Trainer and/or member records the session outcome:
   - What was completed, what was skipped, pain notes, and perceived exertion.
7. System stores:
   - Workout history for future planning.
   - Feedback used to refine next plans.

## 4. Required Member Profile Fields
These are stored per member and used as inputs to plan generation.

### Identity and basics
- `member_name` (string)
- `member_external_id` (optional string; useful if you integrate with an existing gym system)
- `date_of_birth` (date)
- `sex` (choice: `female`, `male`, `unspecified`)
- `height_cm` (optional integer)
- `weight_kg` (optional decimal)

### Training goals and constraints
- `primary_goal` (choice: `strength`, `hypertrophy`, `fat_loss`, `general_fitness`, `rehab_prevention`)
- `secondary_goal` (optional choice)
- `training_experience_level` (choice: `beginner`, `intermediate`, `advanced`)
- `injury_flags` (structured set or JSON of injury types/areas; see safety constraints)
- `equipment_constraints` (structured set; e.g., “avoid barbells”, “limited shoulder mobility”)
- `max_session_minutes_preference` (default preference; can be overridden per session input)

### Preferences and progression history hooks
- `movement_preferences` (optional; e.g., “prefer dumbbells”, “prefer machines”)
- `preferred_rest_policy` (choice: `short`, `standard`, `long` or numeric default)
- `training_frequency_per_week` (integer; used for progression pacing)

## 5. Required Session Input Fields
Session inputs are the trainer-provided fields at the moment of generating a plan. These can be overridden per request.

### Request metadata
- `plan_date` (date; default to today)
- `session_type` (choice: `gym_in_person_one_day`)
- `time_available_minutes` (integer)
- `available_equipment` (structured checklist of equipment present/usable today)
- `current_focus` (choice: `full_body`, `upper`, `lower`, `push`, `pull`, `legs`, `cardio_emphasis`, `restorative_emphasis`)

### Safety and readiness
- `today_pain_level` (integer scale; e.g., 0–10)
- `today_injury_notes` (text; optional but captured)
- `today_energy_level` (choice: `low`, `medium`, `high`)
- `exercise_availability_overrides` (structured list of “avoid” and “must_include” for today)

### Personalization knobs (MVP minimal)
- `progression_style` (choice: `standard`, `conservative`, `aggressive` or mapped to rule presets)
- `any_target_exercises` (optional list; trainer can request specific movements)

## 6. Workout Output Structure
The backend returns a structured workout plan that the tablet UI can render consistently.

### Top-level plan fields
- `plan_id` (UUID)
- `member_id`
- `plan_date`
- `generated_at` (timestamp)
- `status` (choice: `draft`, `approved`, `archived`)
- `summary` (short string for trainer readability)
- `rule_trace` (structured data describing which business rules were applied; kept minimal for MVP)
- `ai_assist_metadata` (optional; indicates AI was used only for allowed selections)

### Plan blocks
Workout blocks should be consistent for rendering and safety:
1. `warmup`
2. `main_work`
3. `cooldown`

Each block contains `items` with a stable schema.

### Exercise item schema
- `item_id` (UUID)
- `block_type` (choice: `warmup`, `main_work`, `cooldown`)
- `exercise_id` (ref to exercise library)
- `exercise_name` (string; denormalized for convenience)
- `movement_pattern` (string; e.g., `squat_pattern`, `hinge_pattern`, `push_vertical`)
- `primary_muscle_group` (string or structured list)
- `equipment_type` (string)
- `prescription`:
  - `sets` (integer)
  - `reps` (string; allow `8-12`, `5`, or `time` formats)
  - `load_guidance` (string; e.g., `RPE target 7`, `leave 1-2 reps in reserve`)
  - `rest_seconds` (integer)
  - `tempo` (optional string; e.g., `2-0-2`)
  - `progression_hint` (string; e.g., “increase load when last set hits top of rep range with RPE <= 8”)
- `safety_notes` (string; concise warnings)
- `substitutions` (optional list of alternative exercises allowed by rules):
  - each alternative includes `exercise_id`, `reason`, and updated `prescription` (or “same prescription” flag)

### Example output (shape)
The exact JSON shape will follow the Django/DRF serializer, but it should always include:
- one `warmup` block
- multiple `main_work` exercise items
- one `cooldown` block
- safety notes for any item flagged as sensitive

## 7. Safety Constraints
All workout generation must pass safety checks before returning a plan.

### Hard constraints (must not violate)
- **Injury filtering:** exercises that conflict with `injury_flags` or today’s “avoid” overrides are excluded.
- **Equipment filtering:** exercises that require unavailable equipment are excluded.
- **Age-aware considerations:** for members under an MVP age threshold, heavy/complex lifts may be constrained to safer progressions (exact threshold is an open question).
- **Known contraindications:** if an exercise is marked as contraindicated for a movement area, it must not appear.
- **Volume limits:** enforce max sets per muscle group and max total main-work sets based on experience level, training frequency, and today’s energy level.
- **Rest bounds:** rest guidance must stay within defined min/max ranges per exercise type.
- **Warmup presence:** a warmup block is required and must include at least one mobility/activation item when pain/injury notes are non-zero.

### Soft constraints (best effort)
- Prefer exercises that match member movement preferences.
- Prefer substitutions that keep technique risk low.
- Keep progression conservative when `progression_style` is `conservative` or energy is `low`.

### AI safety guardrails
- AI can only select from pre-approved candidate exercises and prescriptions produced by business logic.
- AI must not invent new exercises outside the exercise library.
- AI output must be validated by the same safety constraint engine before being accepted into the final plan.
- Store AI usage metadata for auditability (what was allowed, what was chosen, and which rules constrained it).

## 8. MVP Features
1. **Member profile management**
   - Create/edit member profiles via admin or a staff UI.
2. **One-day workout plan generation**
   - Trainer selects member and inputs required session fields.
   - Backend generates a plan using structured rules + optional AI assist.
3. **Plan review and approval**
   - Trainer can accept the plan and mark it as `approved`.
4. **Workout history storage**
   - Save each generated plan and the session outcome.
5. **Workout completion + feedback**
   - Record completion status per exercise and feedback fields (pain/RPE/notes).
6. **Feedback-driven next plan inputs**
   - Use feedback signals (e.g., “pain increased”, “RPE high”, “skipped”) to adjust future prescriptions.
7. **Exercise library administration**
   - Add/edit exercises, movement patterns, equipment mappings, and safety tags.
8. **Tablet-friendly UI**
   - Simple screens: member selection, session input, plan display, workout completion/feedback.

## 9. Non-MVP Features
1. Nutrition tracking and dietary advice.
2. Payments/subscriptions.
3. Voice input.
4. Mobile app (iOS/Android).
5. Fully automated member-only flow without trainer/staff review.
6. Advanced periodization across many weeks with automatic scheduling.
7. Wearable integration and automated biometric ingestion.
8. Workout video/visual coaching library (beyond basic instructions).
9. Multi-language UI (unless required early).
10. Real-time collaborative editing with multiple staff users simultaneously.

## 10. Suggested Django App Structure
Assuming a standard Django project with multiple apps for clear boundaries.

1. `accounts`
   - Authentication models/logic (staff and member accounts).
   - Role mapping (staff vs member).
2. `profiles`
   - Member profile fields and constraints (`MemberProfile`).
3. `gym_content`
   - Exercise library and metadata:
     - `Exercise`, `Equipment`, `MovementPattern`
     - safety tags and contraindication mapping
4. `workout_plans`
   - Plan generation and persisted plans:
     - `WorkoutPlan` (one-day plan)
     - `WorkoutPlanItem` (exercise item blocks)
     - `WorkoutPlanApproval` (if needed)
   - Generation service layer:
     - rule engine entrypoint
     - “AI assist hooks” (optional, strictly constrained)
5. `workout_sessions`
   - Represents a trainer-created session request and completion logging:
     - `WorkoutRequest` (session input payload)
     - `WorkoutSession` (start/end and outcome)
     - `WorkoutSessionItem` (per-exercise completion details)
6. `feedback`
   - Feedback models:
     - pain notes, RPE, what felt good/bad
     - staff notes for adjustments
7. `api`
   - (If using Django REST Framework) serializers and viewsets.
   - Endpoint documentation.
8. `core`
   - Shared utilities:
     - validators for safety constraints
     - rule/prescription helpers
     - common enums

### Implementation notes for Railway deployment
- Use `django-environ` or direct `os.environ` to configure `SECRET_KEY`, DB URL, and allowed hosts.
- Keep AI provider configuration behind env vars (API keys never committed).
- Use SQLite for local dev; switch to Postgres on Railway.

## 11. Open Questions / Assumptions
1. Authentication and workflow
   - Should gym staff create members inside this app, or do we need import from an external system?
2. Member data scope
   - Do we store only profiles and history, or also attendance and scheduling?
3. Exercise library scope for MVP
   - How many exercise templates do we need initially (e.g., 30–100)?
4. Progression logic
   - What progression method should MVP use (simple RPE-based progression vs rep-range progression)?
5. Safety policy details
   - What age threshold triggers conservative exercise constraints?
   - How are contraindications represented (tags per movement area, exercise, or both)?
6. Tablet UI tech
   - Should the MVP UI be Django templates, DRF + simple frontend, or Django + HTMX?
7. AI integration
   - Which AI model/provider will be used, and what is the preferred interaction style (suggest substitutions only, no free-form rewrite)?
8. Feedback mapping
   - How should feedback translate into the next plan (e.g., pain increases -> reduce volume by X, RPE high -> reduce intensity by Y)?
9. Trainer overrides
   - Should trainers be able to create truly custom plans, or only choose from constrained alternatives?
10. “Equipment present” mapping
   - Should equipment selection be manual checklist or inferred from a gym location template?

