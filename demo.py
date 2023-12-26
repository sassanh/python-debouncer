# ruff: noqa: A003, D100, D101, D102, D103, D104, D105, D107, T201
import asyncio
import time

from debouncer import DebounceOptions, debounce


def main() -> None:
    for leading in (False, True):
        for trailing in (False, True):
            for wait in (1, 2):
                for time_window in (None, 0.5, 3):
                    options = DebounceOptions(
                        leading=leading,
                        trailing=trailing,
                        time_window=time_window,
                    )
                    print('---------------------------------------------')
                    print(f'Running demo with options: {options}, wait: {wait}')

                    def timestamp(t0: float) -> str:
                        return f'{time.time() - t0:.2f}'

                    @debounce(wait=wait, options=options)
                    async def demo_function(t0: float, arg: str) -> None:
                        print(
                            f"""{timestamp(t0)
                            }: Demo function called with argument: {arg}""",
                        )

                    async def demo() -> None:
                        t0 = time.time()

                        print(
                            f"{timestamp(t0)}: Calling demo_function with 'First call'",
                        )
                        await demo_function(t0, 'First call')
                        await asyncio.sleep(1.5)
                        print(
                            f"""{
                            timestamp(t0)}: Calling demo_function with 'Second call'""",
                        )
                        await demo_function(t0, 'Second call')
                        await asyncio.sleep(3)
                        print(
                            f"{timestamp(t0)}: Calling demo_function with 'Third call'",
                        )
                        await demo_function(t0, 'Third call')
                        while True:
                            all_tasks = {
                                task
                                for task in asyncio.all_tasks()
                                if task is not asyncio.current_task()
                            }
                            if len(all_tasks) == 0:
                                return
                            await asyncio.wait(all_tasks)

                    asyncio.run(demo())
