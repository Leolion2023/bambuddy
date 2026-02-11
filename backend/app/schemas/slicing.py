"""Pydantic schemas for OrcaSlicer slicing jobs."""

from datetime import datetime

from pydantic import BaseModel, Field


class SliceRequest(BaseModel):
    """Request to slice a file."""

    file_id: int | None = Field(None, description="Library file ID to slice")
    archive_id: int | None = Field(None, description="Archive ID to slice")
    filament_preset_id: int | None = Field(None, description="Filament preset to use")
    printer_preset_id: int | None = Field(None, description="Printer preset to use")
    process_preset_id: int | None = Field(None, description="Process preset to use")
    auto_push_to_archive: bool = Field(True, description="Automatically push result to archive")


class SliceJobStatus(BaseModel):
    """Status of a slicing job."""

    job_id: str
    status: str  # queued, processing, completed, failed
    progress: int  # 0-100
    error_message: str | None = None
    input_filename: str
    output_filename: str | None = None
    archive_id: int | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class SliceJobResponse(BaseModel):
    """Response when submitting a slice job."""

    success: bool
    job_id: str
    message: str


class OrcaSlicerStatus(BaseModel):
    """OrcaSlicer service connection status."""

    enabled: bool
    available: bool
    message: str | None = None
    orcaslicer_path: str | None = None


class SliceJobList(BaseModel):
    """List of slicing jobs."""

    jobs: list[SliceJobStatus]
    total: int
