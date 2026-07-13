from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Union


@dataclass
class ComponentSubscribeEvent:
    component: str
    topic: str
    name: Literal["component.subscribe"] = field(default="component.subscribe", init=False)


@dataclass
class ComponentLoopEvent:
    component: str
    function: str
    name: Literal["component.loop"] = field(default="component.loop", init=False)


@dataclass
class ComponentStartEvent:
    correlation_id: str
    url: str
    component: str
    retrying: bool
    retries: int
    topic: str | None = None
    function: str | None = None
    name: Literal["component.start"] = field(default="component.start", init=False)


@dataclass
class ComponentFinishEvent:
    correlation_id: str
    url: str
    component: str
    duration_ms: float
    retrying: bool
    retries: int
    topic: str | None = None
    function: str | None = None
    name: Literal["component.finish"] = field(default="component.finish", init=False)


@dataclass
class ComponentErrorEvent:
    correlation_id: str
    url: str
    component: str
    error: str
    retriable: bool
    retrying: bool
    retries: int
    unexpected: bool
    exception: BaseException | None = None
    name: Literal["component.error"] = field(default="component.error", init=False)


@dataclass
class ComponentPublishEvent:
    component: str
    topic: str
    urls: list[tuple[str, int]]  # (address, priority)
    delay: int | None = None
    name: Literal["component.publish"] = field(default="component.publish", init=False)


@dataclass
class RuleStartEvent:
    correlation_id: str
    url: str
    component: str
    rule: str
    name: Literal["rule.start"] = field(default="rule.start", init=False)


@dataclass
class RuleFinishEvent:
    correlation_id: str
    url: str
    component: str
    rule: str
    passed: bool
    name: Literal["rule.finish"] = field(default="rule.finish", init=False)


@dataclass
class RuleErrorEvent:
    correlation_id: str
    url: str
    component: str
    rule: str
    error: str
    retriable: bool
    exception: BaseException | None = None
    name: Literal["rule.error"] = field(default="rule.error", init=False)


@dataclass
class DeduplicatorStartEvent:
    correlation_id: str
    url: str
    component: str
    deduplicator: str
    name: Literal["deduplicator.start"] = field(default="deduplicator.start", init=False)


@dataclass
class DeduplicatorFinishEvent:
    correlation_id: str
    url: str
    component: str
    deduplicator: str
    seen: bool
    name: Literal["deduplicator.finish"] = field(default="deduplicator.finish", init=False)


@dataclass
class DeduplicatorErrorEvent:
    correlation_id: str
    url: str
    component: str
    deduplicator: str
    error: str
    retriable: bool
    exception: BaseException | None = None
    name: Literal["deduplicator.error"] = field(default="deduplicator.error", init=False)


@dataclass
class MiddlewareStartEvent:
    correlation_id: str
    url: str
    component: str
    middleware: str
    name: Literal["middleware.start"] = field(default="middleware.start", init=False)


@dataclass
class MiddlewareFinishEvent:
    correlation_id: str
    url: str
    component: str
    middleware: str
    data: dict[str, Any]
    name: Literal["middleware.finish"] = field(default="middleware.finish", init=False)


@dataclass
class MiddlewareErrorEvent:
    correlation_id: str
    url: str
    component: str
    middleware: str
    error: str
    retriable: bool
    exception: BaseException | None = None
    name: Literal["middleware.error"] = field(default="middleware.error", init=False)


@dataclass
class FilterStartEvent:
    correlation_id: str
    url: str
    component: str
    filter: str
    name: Literal["filter.start"] = field(default="filter.start", init=False)


@dataclass
class FilterFinishEvent:
    correlation_id: str
    url: str
    component: str
    filter: str
    passed: bool
    name: Literal["filter.finish"] = field(default="filter.finish", init=False)


@dataclass
class FilterErrorEvent:
    correlation_id: str
    url: str
    component: str
    filter: str
    error: str
    retriable: bool
    exception: BaseException | None = None
    name: Literal["filter.error"] = field(default="filter.error", init=False)


@dataclass
class PrioritizerStartEvent:
    correlation_id: str
    url: str
    component: str
    prioritizer: str
    name: Literal["prioritizer.start"] = field(default="prioritizer.start", init=False)


@dataclass
class PrioritizerFinishEvent:
    correlation_id: str
    url: str
    component: str
    prioritizer: str
    priority: int
    name: Literal["prioritizer.finish"] = field(default="prioritizer.finish", init=False)


@dataclass
class PrioritizerErrorEvent:
    correlation_id: str
    url: str
    component: str
    prioritizer: str
    error: str
    retriable: bool
    exception: BaseException | None = None
    name: Literal["prioritizer.error"] = field(default="prioritizer.error", init=False)


Event = Union[
    ComponentSubscribeEvent, ComponentLoopEvent,
    ComponentStartEvent, ComponentFinishEvent, ComponentErrorEvent,
    ComponentPublishEvent,
    RuleStartEvent, RuleFinishEvent, RuleErrorEvent,
    DeduplicatorStartEvent, DeduplicatorFinishEvent, DeduplicatorErrorEvent,
    MiddlewareStartEvent, MiddlewareFinishEvent, MiddlewareErrorEvent,
    FilterStartEvent, FilterFinishEvent, FilterErrorEvent,
    PrioritizerStartEvent, PrioritizerFinishEvent, PrioritizerErrorEvent,
]
