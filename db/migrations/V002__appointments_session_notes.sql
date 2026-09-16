-- ChronoLog V002 — appointments + session_notes (TSK-013).
--
-- Idempotent: safe to re-apply (`IF NOT EXISTS` throughout).
-- Apply order: AFTER V001 (FKs into users/clients). See db/README.md.
--
-- Decisions (full rationale in verify/task13_test.md, Section 1):
--   * appointments.client_id ON DELETE CASCADE (not RESTRICT): keeps the
--     user -> clients -> appointments -> notes cascade chain consistent so a
--     tenant wipe never strands orphans. No delete use-case exists in MUST
--     scope (T7-D4), so history loss on client delete is out-of-scope risk.
--   * Overlap prevention is application-level (ScheduleAppointment +
--     list_overlapping in TSK-014), NOT a GiST exclusion constraint: no
--     btree_gist extension, no dual-enforcement drift, cancelled/completed
--     windows stay queryable. Minimum DB guard: ends_at > starts_at.
--   * session_notes is a SEPARATE table with UNIQUE(appointment_id) (1:1 with
--     the appointment aggregate per T10-D1): keeps appointments rows narrow,
--     allows updated_at tracking, and gives TSK-014 adapter flexibility
--     (aggregate saved in one transaction across both tables).
--   * session_notes.user_id is denormalized (REFERENCES users + indexed) so
--     every notes query can be AuthZ-scoped without joining appointments.
--   * status values are lowercase ('scheduled','completed','cancelled') to match
--     the AppointmentStatus domain enum exactly.

CREATE TABLE IF NOT EXISTS appointments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients (id) ON DELETE CASCADE,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'completed', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT appointments_window_check CHECK (ends_at > starts_at)
);

-- Overlap/history fast paths for TSK-014:
-- (user_id, starts_at) serves list_by_user_id + list_overlapping range scans;
-- (client_id) serves GetClientHistory (list_by_client_and_user_id).
CREATE INDEX IF NOT EXISTS idx_appointments_user_starts
    ON appointments (user_id, starts_at);
CREATE INDEX IF NOT EXISTS idx_appointments_client
    ON appointments (client_id);

CREATE TABLE IF NOT EXISTS session_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appointment_id UUID NOT NULL UNIQUE
        REFERENCES appointments (id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    content TEXT NOT NULL
        CHECK (char_length(btrim(content)) >= 1 AND char_length(content) <= 5000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    -- NOTE: updated_at maintenance is application-level (TSK-014 adapter sets it
    -- on edit); no trigger, to keep migrations dependency-free and obvious.
);

-- AuthZ fast path for notes lookups scoped by user_id. (appointment_id lookups
-- are already covered by the UNIQUE constraint's backing index.)
CREATE INDEX IF NOT EXISTS idx_session_notes_user_id ON session_notes (user_id);
