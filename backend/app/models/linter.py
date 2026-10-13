from pydantic import BaseModel
from typing import List, Optional, Dict

class LinterIssue(BaseModel):
    type: str # "PUNCTUATION" | "LAYOUT" | "FONT" | "MARGINS" | "REFERENCE" | "STYLE"
    severity: str # "ERROR" | "WARNING" | "INFO"
    message: str
    location: str
    fix_suggestion: Optional[str] = None

class LinterMetrics(BaseModel):
    margins_mm: Dict[str, float]
    page_count_estimate: int
    figures_count: int
    tables_count: int
    listings_count: int
    empty_paragraphs_count: int

class LinterResult(BaseModel):
    is_valid: bool
    status: str # "ready" | "needs_review" | "invalid"
    score: int # 0-100
    errors: List[LinterIssue]
    warnings: List[LinterIssue]
    metrics: LinterMetrics
