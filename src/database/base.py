from datetime import UTC, datetime
from enum import IntEnum
from typing import Any, Type
from uuid import UUID, uuid4

from sqlalchemy import TIMESTAMP, Integer, TypeDecorator, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    MappedAsDataclass,
    mapped_column,
)


class Base(AsyncAttrs, MappedAsDataclass, DeclarativeBase):
    type_annotation_map = {
        dict[str, Any]: JSONB,
        datetime: TIMESTAMP(timezone=True),
    }


class BaseWithTimestamps(Base):
    __abstract__ = True

    created_at: Mapped[datetime] = mapped_column(
        init=False,
        default_factory=lambda: datetime.now(UTC),
        insert_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        init=False, default=None, onupdate=func.now()
    )


class BaseEntity(BaseWithTimestamps):
    __abstract__ = True

    id: Mapped[UUID] = mapped_column(
        init=False, primary_key=True, default_factory=uuid4
    )


class BaseEntityWithIntId(BaseWithTimestamps):
    __abstract__ = True

    id: Mapped[int] = mapped_column(init=True, primary_key=True)


class SQLAlchemyIntEnum(TypeDecorator):
    impl = Integer
    cache_ok = True

    def __init__(self, enum: Type[IntEnum], *args, **kwargs):
        self.enum = enum
        super().__init__(*args, **kwargs)

    def process_bind_param(self, value, dialect):
        if isinstance(value, int):
            return value

        return value.value

    def process_result_value(self, value, dialect) -> IntEnum | None:
        try:
            return self.enum(value)
        except ValueError:
            return None
