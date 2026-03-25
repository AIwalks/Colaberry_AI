from sqlalchemy.orm import Session

from config.database import SessionLocal
from core.fingerprint.patterns import BehaviorPattern
from core.fingerprint.service import FingerprintService


db: Session = SessionLocal()

pattern = BehaviorPattern(
    name="test_pattern",
    description="demo",
    thresholds={
        "logins": 3,
        "score": 0.7,
    },
)

metrics = {
    "logins": 5,
    "score": 0.8,
}

service = FingerprintService()

record = service.evaluate_and_store(
    db=db,
    entity_type="student",
    entity_id="123",
    pattern=pattern,
    metrics=metrics,
)

print(record.id, record.pattern_name, record.score)
