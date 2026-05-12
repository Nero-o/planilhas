from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Literal, Optional
import uuid


Source = Literal["sicoob", "bs2", "bb", "conta_simples", "c6"]
Confidence = Literal["green", "yellow", "red"]
ClassifierKind = Literal["rule", "llm", "manual"]


@dataclass
class Transaction:
    source: Source
    raw_row: dict
    data: datetime
    tipo: str
    beneficiario: str
    valor: float
    descricao: Optional[str] = None
    observacoes: Optional[str] = None
    fluxo_caixa: Optional[str] = None
    empresa: Optional[str] = None
    confidence: Confidence = "red"
    reasoning: str = ""
    classifier: Optional[ClassifierKind] = None
    _id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict:
        return asdict(self)
