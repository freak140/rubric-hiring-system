import enum


class AppRole(enum.Enum):
    chairman = "chairman"
    principal = "principal"
    interviewer = "interviewer"
    hr = "hr"


class RoleType(enum.Enum):
    teaching = "teaching"
    non_teaching = "non_teaching"


class OpeningStatus(enum.Enum):
    draft = "draft"
    open = "open"
    filled = "filled"
    closed = "closed"


class ScorecardStatus(enum.Enum):
    draft = "draft"
    approved = "approved"


class ScorecardItemKind(enum.Enum):
    outcome = "outcome"
    competency = "competency"


class CandidateSource(enum.Enum):
    referral = "referral"
    network = "network"
    job_board = "job_board"
    recruiter = "recruiter"
    other = "other"


class ApplicationStage(enum.Enum):
    sourced = "sourced"
    screening = "screening"
    who_interview = "who_interview"
    focused = "focused"
    references = "references"
    decision = "decision"
    offer = "offer"
    hired = "hired"
    rejected = "rejected"
    withdrawn = "withdrawn"


class InterviewType(enum.Enum):
    screening = "screening"
    who = "who"
    focused = "focused"
    demo_lesson = "demo_lesson"


class InterviewStatus(enum.Enum):
    assigned = "assigned"
    completed = "completed"
    released = "released"


class ScreeningOutcome(enum.Enum):
    pass_ = "pass"
    fail = "fail"


class Grade(enum.Enum):
    A = "A"
    B = "B"
    C = "C"


class RefereeRelationship(enum.Enum):
    former_manager = "former_manager"
    peer = "peer"
    direct_report = "direct_report"
    other = "other"


class ReferenceStatus(enum.Enum):
    named = "named"
    completed = "completed"


class CheckStatus(enum.Enum):
    pending = "pending"
    cleared = "cleared"
    flagged = "flagged"


class DecisionOutcome(enum.Enum):
    hire = "hire"
    no_hire = "no_hire"
