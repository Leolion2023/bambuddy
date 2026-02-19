"""Model for OrcaSlicer slicing jobs."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class SlicingJob(Base):
    """A slicing job submitted to OrcaSlicer."""

    __tablename__ = "slicing_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Job identification
    job_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer)

    # Input file information
    input_filename: Mapped[str] = mapped_column(String(500))
    input_file_path: Mapped[str] = mapped_column(String(1000))

    # Slicing configuration
    filament_preset_id: Mapped[int | None] = mapped_column(Integer)
    printer_preset_id: Mapped[int | None] = mapped_column(Integer)
    process_preset_id: Mapped[int | None] = mapped_column(Integer)
    filament_type: Mapped[str | None] = mapped_column(String(50))

    # Output information
    output_filename: Mapped[str | None] = mapped_column(String(500))
    output_file_path: Mapped[str | None] = mapped_column(String(1000))

    # Status tracking
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued, processing, completed, failed
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    error_message: Mapped[str | None] = mapped_column(Text)

    # Options
    auto_push_to_archive: Mapped[bool] = mapped_column(default=False)
    archive_id: Mapped[int | None] = mapped_column(Integer)  # If pushed to archive

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
