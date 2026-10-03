"""Relational data model (SQLAlchemy).  SQLite by default; set DATABASE_URL
(e.g. postgresql+psycopg://user:pw@host/timetable) to use PostgreSQL."""
import os
from datetime import datetime

from sqlalchemy import (JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String,
                        UniqueConstraint, create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(__file__), 'timetable.db')}")
engine = create_engine(URL, connect_args={"check_same_thread": False} if URL.startswith("sqlite") else {})
Session = sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()


def fk(table, **kw):
    return Column(Integer, ForeignKey(f"{table}.id", ondelete="CASCADE"), **kw)


class College(Base):
    __tablename__ = "college"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)


class Department(Base):
    __tablename__ = "department"
    id = Column(Integer, primary_key=True)
    college_id = fk("college")
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)


class Program(Base):
    __tablename__ = "program"
    id = Column(Integer, primary_key=True)
    department_id = fk("department")
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)


class AcademicYear(Base):
    __tablename__ = "academic_year"
    id = Column(Integer, primary_key=True)
    label = Column(String, unique=True, nullable=False)


class Semester(Base):
    __tablename__ = "semester"
    id = Column(Integer, primary_key=True)
    academic_year_id = fk("academic_year")
    number = Column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint("academic_year_id", "number"),)


class Room(Base):
    """Classrooms and labs (kind = CLASSROOM | LAB; labs carry a lab_type)."""
    __tablename__ = "room"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String)
    kind = Column(String, nullable=False)
    capacity = Column(Integer, nullable=False)
    lab_type = Column(String)
    department_id = fk("department", nullable=True)


class Division(Base):
    __tablename__ = "division"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)        # SE-CE-A
    program_id = fk("program")
    semester_id = fk("semester")
    year_level = Column(String, nullable=False)                # SE / TE / BE
    name = Column(String, nullable=False)                      # A
    strength = Column(Integer, nullable=False)
    home_room_id = fk("room", nullable=True)
    program = relationship("Program")
    semester = relationship("Semester")
    batches = relationship("StudentBatch", order_by="StudentBatch.name")


class StudentBatch(Base):
    __tablename__ = "student_batch"
    id = Column(Integer, primary_key=True)
    division_id = fk("division")
    name = Column(String, nullable=False)
    strength = Column(Integer, nullable=False)


class Subject(Base):
    __tablename__ = "subject"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    department_id = fk("department")
    semester_no = Column(Integer)
    credits = Column(Float, nullable=False)
    lecture_sessions_per_week = Column(Integer, default=0)
    tutorial_sessions_per_week = Column(Integer, default=0)
    practical_sessions_per_week = Column(Integer, default=0)
    practical_duration_periods = Column(Integer, default=2)
    lab_type = Column(String)
    is_core = Column(Boolean, default=False)
    morning_preferred = Column(Boolean, default=False)


class SubjectRequirement(Base):
    """What a division (or one batch of it) must receive per week for a subject component.
    Defaults come from Subject but can be overridden per division."""
    __tablename__ = "subject_requirement"
    id = Column(Integer, primary_key=True)
    division_id = fk("division")
    subject_id = fk("subject")
    batch_id = fk("student_batch", nullable=True)
    component = Column(String, nullable=False)                 # L | T | P
    sessions_per_week = Column(Integer, nullable=False)
    duration_periods = Column(Integer, default=1)
    division = relationship("Division")
    subject = relationship("Subject")
    assignment = relationship("FacultyClassAssignment", uselist=False, back_populates="requirement")


class Faculty(Base):
    __tablename__ = "faculty"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    department_id = fk("department")
    designation = Column(String)
    max_per_day = Column(Integer, default=5)
    max_per_week = Column(Integer, default=20)
    min_per_week = Column(Integer, default=0)
    max_consecutive = Column(Integer, default=3)
    active = Column(Boolean, default=True)
    subjects = relationship("Subject", secondary="faculty_subject")


class FacultySubject(Base):
    """Faculty authorized/qualified to teach a subject (also governs substitute eligibility)."""
    __tablename__ = "faculty_subject"
    faculty_id = fk("faculty", primary_key=True)
    subject_id = fk("subject", primary_key=True)


class FacultyClassAssignment(Base):
    """Who teaches a requirement.  auto_assigned = chosen by the workload balancer."""
    __tablename__ = "faculty_class_assignment"
    id = Column(Integer, primary_key=True)
    requirement_id = fk("subject_requirement", unique=True)
    faculty_id = fk("faculty", nullable=True)
    auto_assigned = Column(Boolean, default=False)
    requirement = relationship("SubjectRequirement", back_populates="assignment")


class WorkingDay(Base):
    __tablename__ = "working_day"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    order = Column(Integer, nullable=False)


class TimeSlot(Base):
    __tablename__ = "time_slot"
    id = Column(Integer, primary_key=True)
    index = Column(Integer, unique=True, nullable=False)
    start = Column(String, nullable=False)
    end = Column(String, nullable=False)
    is_break = Column(Boolean, default=False)
    label = Column(String)


class FacultyAvailability(Base):
    __tablename__ = "faculty_availability"
    id = Column(Integer, primary_key=True)
    faculty_id = fk("faculty")
    day_id = fk("working_day")
    slot_id = fk("time_slot")
    kind = Column(String, nullable=False)                      # UNAVAILABLE | PREFERRED


class FacultyAbsence(Base):
    """One row per absent slot; slot_id NULL = full day."""
    __tablename__ = "faculty_absence"
    id = Column(Integer, primary_key=True)
    faculty_id = fk("faculty")
    date = Column(Date, nullable=False)
    slot_id = fk("time_slot", nullable=True)
    reason = Column(String)
    created_at = Column(DateTime, default=datetime.now)


class GenerationRun(Base):
    __tablename__ = "generation_run"
    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, default=datetime.now)
    status = Column(String)
    seed = Column(Integer)
    scope = Column(JSON)
    generation_time = Column(Float)
    metrics = Column(JSON)
    issues = Column(JSON)


class Timetable(Base):
    __tablename__ = "timetable"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    status = Column(String, default="DRAFT")                   # DRAFT | ACTIVE | ARCHIVED
    created_at = Column(DateTime, default=datetime.now)
    generation_run_id = fk("generation_run", nullable=True)
    entries = relationship("TimetableEntry", cascade="all, delete-orphan")


class TimetableEntry(Base):
    """One scheduled session.  locked=True entries survive regeneration (lecture/day/class/
    faculty/practical locks are all expressed by locking the matching entries)."""
    __tablename__ = "timetable_entry"
    id = Column(Integer, primary_key=True)
    timetable_id = fk("timetable")
    requirement_id = fk("subject_requirement")
    division_id = fk("division")
    batch_id = fk("student_batch", nullable=True)
    subject_id = fk("subject")
    faculty_id = fk("faculty")
    room_id = fk("room")
    day_id = fk("working_day")
    slot_id = fk("time_slot")
    duration = Column(Integer, default=1)
    component = Column(String, nullable=False)
    locked = Column(Boolean, default=False)
    explanation = Column(JSON)


class Substitution(Base):
    """Date-specific change to a weekly entry: SUBSTITUTED / CANCELLED / RESCHEDULED."""
    __tablename__ = "substitution"
    id = Column(Integer, primary_key=True)
    entry_id = fk("timetable_entry")
    date = Column(Date, nullable=False)
    original_faculty_id = fk("faculty")
    substitute_faculty_id = fk("faculty", nullable=True)
    status = Column(String, nullable=False)
    new_date = Column(Date)
    new_slot_id = fk("time_slot", nullable=True)
    new_room_id = fk("room", nullable=True)
    reason = Column(String)
    reasons = Column(JSON)                                     # why this candidate (explainability)
    workload_override = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)


class ConstraintConfiguration(Base):
    __tablename__ = "constraint_configuration"
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    description = Column(String)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    ts = Column(DateTime, default=datetime.now)
    user = Column(String, default="admin")
    action = Column(String, nullable=False)
    previous = Column(JSON)
    new = Column(JSON)
    reason = Column(String)


def init():
    Base.metadata.create_all(engine)
