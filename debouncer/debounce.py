# ruff: noqa: A003, D100, D101, D102, D103, D104, D105, D107
# This implementation is msotly based on this Lodash implementation:
# https://github.com/lodash/lodash/blob/4.17.15-npm/debounce.js
from __future__ import annotations

import asyncio
import time
import weakref
from asyncio.coroutines import iscoroutine
from dataclasses import dataclass
from functools import wraps
from types import MethodType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Generic,
    Protocol,
    cast,
)

from immutable import Immutable
from typing_extensions import ParamSpec, TypeVar

if TYPE_CHECKING:
    from asyncio.tasks import Task


def now() -> float:
    return time.time()


Args = ParamSpec('Args')
Result = TypeVar('Result', infer_variance=True)


class Debounced(Protocol, Generic[Args, Result]):
    def __call__(
        self: Debounced,
        *args: Args.args,
        **kwargs: Args.kwargs,
    ) -> Result: ...

    def cancel(self: Debounced) -> None: ...

    def flush(self: Debounced) -> Result: ...


class DebounceOptions(Immutable):
    leading: bool = False
    trailing: bool = True
    time_window: float | None = None
    keep_ref: bool = True


@dataclass
class DebounceState(Generic[Args, Result]):
    func: (
        Callable[Args, Coroutine[Any, Any, Result] | Result]
        | weakref.ref[Callable[Args, Coroutine[Any, Any, Result] | Result]]
        | weakref.WeakMethod
    )
    wait: float
    leading: bool = False
    trailing: bool = True
    time_window: float | None = None
    result: Result | None = None
    timer_task: Task | None = None
    last_args: tuple[tuple[Args.args, ...], dict[str, Args.kwargs]] | None = (  # pyright: ignore  # noqa: PGH003
        None
    )
    last_call_time: float | None = None
    last_invoke_time: float = 0


async def _leading_edge(
    state: DebounceState[Args, Result],
    time: float,
) -> Result | None:
    state.last_invoke_time = time
    state.timer_task = asyncio.create_task(_timer_expired(state))
    return await _invoke_func(state, time) if state.leading else state.result


def _remaining_wait(state: DebounceState[Args, Result], time: float) -> float:
    time_since_last_call = time - (state.last_call_time or time)
    time_since_last_invoke = time - state.last_invoke_time
    time_waiting = state.wait - time_since_last_call

    return (
        time_waiting
        if state.time_window is None
        else min(time_waiting, state.time_window - time_since_last_invoke)
    )


def _should_invoke(state: DebounceState[Args, Result], time: float) -> bool:
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


async def _timer_expired(state: DebounceState[Args, Result]) -> None:
    current_time = now()
    if _should_invoke(state, current_time):
        await _trailing_edge(state, current_time)
    else:

        async def act() -> None:
            await asyncio.sleep(_remaining_wait(state, current_time))
            await _timer_expired(state)

        state.timer_task = asyncio.create_task(act())


async def _invoke_func(
    state: DebounceState[Args, Result],
    time: float,
) -> Result | None:
    state.last_invoke_time = time
    if not state.last_args:
        return None
    func = state.func() if isinstance(state.func, weakref.ref) else state.func
    if func:
        result = func(
            *state.last_args[0],
            **state.last_args[1],
        )
        if iscoroutine(result):
            result = await result
        state.result = result
    else:
        msg = 'Function has been garbage collected'
        raise RuntimeError(msg)
    state.last_args = None
    return state.result


async def _trailing_edge(
    state: DebounceState[Args, Result],
    time: float,
) -> Result | None:
    state.timer_task = None

    if state.trailing and state.last_args:
        return await _invoke_func(state, time)

    state.last_args = None
    return state.result


def cancel(state: DebounceState[Args, Result]) -> None:
    if state.timer_task:
        state.timer_task.cancel()
    state.last_invoke_time = 0
    state.last_args = state.last_call_time = state.timer_task = None


async def flush(state: DebounceState[Args, Result]) -> Result | None:
    return (
        state.result if state.timer_task is None else await _trailing_edge(state, now())
    )


def debounce(
    wait: float,
    options: DebounceOptions | None = None,
) -> Callable[
    [Callable[Args, Coroutine[Any, Any, Result] | Result]],
    Debounced[Args, Coroutine[Any, Any, Result | None]],
]:
    debounce_options = options or DebounceOptions()

    def decorator(
        func: Callable[Args, Coroutine[Any, Any, Result] | Result],
    ) -> Debounced[Args, Coroutine[Any, Any, Result | None]]:
        if debounce_options.keep_ref:
            func_ref = func
        elif isinstance(func, MethodType):
            func_ref = weakref.WeakMethod(func)
        else:
            func_ref = weakref.ref(func)
        state = DebounceState[Args, Result](
            func=func_ref,
            wait=wait,
            leading=debounce_options.leading,
            time_window=debounce_options.time_window,
            trailing=debounce_options.trailing,
        )

        state.last_args = None

        @wraps(cast(Callable[Args, Coroutine[Any, Any, Result]], func))
        async def wrapper_(*args: Args.args, **kwargs: Args.kwargs) -> Result | None:
            current_time = now()
            is_invoking = _should_invoke(state, current_time)

            state.last_args = (args, kwargs)
            state.last_call_time = current_time

            if is_invoking:
                if state.timer_task is None:
                    return await _leading_edge(state, state.last_call_time)
                if state.time_window is not None:
                    state.timer_task.cancel()
                    state.timer_task = asyncio.create_task(_timer_expired(state))
                    return await _invoke_func(state, state.last_call_time)

            if state.timer_task is None:
                state.timer_task = asyncio.create_task(_timer_expired(state))

            return state.result

        wrapper = cast(Debounced, wrapper_)
        if isinstance(func, MethodType):
            wrapper = cast(Debounced, MethodType(wrapper, func.__self__))
        wrapper.cancel = lambda: cancel(state)
        wrapper.flush = lambda: flush(state)
        return wrapper

    return decorator
