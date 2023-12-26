# ruff: noqa: A003, D100, D101, D102, D103, D104, D105, D107
# This implementation is msotly based on this Lodash implementation:
# https://github.com/lodash/lodash/blob/4.17.15-npm/debounce.js
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from functools import wraps
from typing import (
    TYPE_CHECKING,
    Awaitable,
    Callable,
    Generic,
    ParamSpec,
    Protocol,
    TypeVar,
    cast,
)

from immutable import Immutable

if TYPE_CHECKING:
    from asyncio.tasks import Task


def now() -> float:
    return time.time()


Args = ParamSpec('Args')
Result_co = TypeVar('Result_co', covariant=True)


class Debounced(Protocol, Generic[Args, Result_co]):
    def __call__(self: Debounced, *args: Args.args, **kwargs: Args.kwargs) -> Result_co:
        ...

    def cancel(self: Debounced) -> None:
        ...

    def flush(self: Debounced) -> Result_co:
        ...


class DebounceOptions(Immutable):
    leading: bool = False
    trailing: bool = True
    time_window: float | None = None


@dataclass
class DebounceState(Generic[Args, Result_co]):
    func: Callable[Args, Awaitable[Result_co]]
    wait: float
    leading: bool = False
    trailing: bool = True
    time_window: float | None = None
    result: Result_co | None = None
    timer_task: Task | None = None
    last_args: tuple[tuple[Args.args, ...], dict[str, Args.kwargs]] | None = None
    last_call_time: float | None = None
    last_invoke_time: float = 0


async def leading_edge(
    state: DebounceState[Args, Result_co],
    time: float,
) -> Result_co | None:
    state.last_invoke_time = time
    state.timer_task = asyncio.create_task(timer_expired(state))
    return await invoke_func(state, time) if state.leading else state.result


def remaining_wait(state: DebounceState[Args, Result_co], time: float) -> float:
    time_since_last_call = time - (state.last_call_time or time)
    time_since_last_invoke = time - state.last_invoke_time
    time_waiting = state.wait - time_since_last_call

    return (
        time_waiting
        if state.time_window is None
        else min(time_waiting, state.time_window - time_since_last_invoke)
    )


def should_invoke(state: DebounceState[Args, Result_co], time: float) -> bool:
    if state.last_call_time is None:
        return True

    time_since_last_call = time - state.last_call_time
    time_since_last_invoke = time - state.last_invoke_time

    return (
        state.last_call_time is None
        or time_since_last_call >= state.wait
        or time_since_last_call < 0
        or (
            state.time_window is not None
            and time_since_last_invoke >= state.time_window
        )
    )


async def timer_expired(state: DebounceState[Args, Result_co]) -> None:
    current_time = now()
    if should_invoke(state, current_time):
        await trailing_edge(state, current_time)
    else:

        async def act() -> None:
            await asyncio.sleep(remaining_wait(state, current_time))
            await timer_expired(state)

        state.timer_task = asyncio.create_task(act())


async def invoke_func(
    state: DebounceState[Args, Result_co],
    time: float,
) -> Result_co | None:
    state.last_invoke_time = time
    if not state.last_args:
        return None
    state.result = await state.func(
        *state.last_args[0],
        **state.last_args[1],
    )
    state.last_args = None
    return state.result


async def trailing_edge(
    state: DebounceState[Args, Result_co],
    time: float,
) -> Result_co | None:
    state.timer_task = None

    if state.trailing and state.last_args:
        return await invoke_func(state, time)

    state.last_args = None
    return state.result


def debounce(
    wait: float,
    options: DebounceOptions | None = None,
) -> Callable[
    [Callable[Args, Awaitable[Result_co]]],
    Debounced[Args, Awaitable[Result_co | None]],
]:
    options = options or DebounceOptions()

    def decorator(
        func: Callable[Args, Awaitable[Result_co]],
    ) -> Debounced[Args, Awaitable[Result_co | None]]:
        state = DebounceState[Args, Result_co](
            func=func,
            wait=wait,
            leading=options.leading,
            time_window=options.time_window,
            trailing=options.trailing,
        )

        state.last_args = None

        @wraps(func)
        async def wrapper_(*args: Args.args, **kwargs: Args.kwargs) -> Result_co | None:
            current_time = now()
            is_invoking = should_invoke(state, current_time)

            state.last_args = (args, kwargs)
            state.last_call_time = current_time

            if is_invoking:
                if state.timer_task is None:
                    return await leading_edge(state, state.last_call_time)
                if state.time_window is not None:
                    state.timer_task.cancel()
                    state.timer_task = asyncio.create_task(timer_expired(state))
                    return await invoke_func(state, state.last_call_time)

            if state.timer_task is None:
                state.timer_task = asyncio.create_task(timer_expired(state))

            return state.result

        def cancel() -> None:
            if state.timer_task:
                state.timer_task.cancel()
            state.last_invoke_time = 0
            state.last_args = state.last_call_time = state.timer_task = None

        async def flush() -> Result_co | None:
            return (
                state.result
                if state.timer_task is None
                else await trailing_edge(state, now())
            )

        wrapper = cast(Debounced, wrapper_)
        wrapper.cancel = cancel
        wrapper.flush = flush
        return wrapper

    return decorator
