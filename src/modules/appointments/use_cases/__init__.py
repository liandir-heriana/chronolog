"""ChronoLog appointments use cases (depend only on domain ports)."""

from src.modules.appointments.use_cases.complete_appointment import CompleteAppointment
from src.modules.appointments.use_cases.schedule_appointment import ScheduleAppointment

__all__ = ["CompleteAppointment", "ScheduleAppointment"]
