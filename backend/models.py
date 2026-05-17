from sqlalchemy import Column, String, Integer, Text, DateTime, JSON
from sqlalchemy.sql import func
from backend.database import Base


class Run(Base):
    __tablename__ = "runs"

    id = Column(String, primary_key=True, index=True)
    topics = Column(JSON, default=list)
    urls_provided = Column(JSON, default=list)
    role = Column(String, default="general")
    status = Column(String, default="pending")
    current_step_detail = Column(String, nullable=True)
    report_json = Column(JSON, nullable=True)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SourceFetch(Base):
    __tablename__ = "source_fetches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, index=True)
    url = Column(String)
    fetch_status = Column(String)  # success / failed / scanned_pdf
    extracted_text_length = Column(Integer, default=0)
    error_message = Column(String, nullable=True)


class Claim(Base):
    __tablename__ = "claims"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, index=True)
    claim = Column(Text)
    source_url = Column(String)
    verdict = Column(String)  # supported / partial / unsupported
    verdict_reason = Column(Text)
