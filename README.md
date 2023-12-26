# Asyncio Debouncer

## Description

This Python package provides a debounce decorator using asyncio, ensuring function execution is managed within the asyncio event loop without spawning new threads. It's designed for rate-limiting function calls in asynchronous Python applications.

## 📦 Installation

### Pip

```bash
pip install python-debouncer
```

### Poetry

```bash
poetry add python-debouncer
```

## 🚀 Usage

Import the decorator and apply it to your async functions:

```python
from debouncer import DebounceOptions, debounce

@debounce(wait=.5, options=DebounceOptions(trailing=True, leading=False, time_window=3))
async def your_function():
    # Function body
```

[Lodash documentation](https://lodash.com/docs/4.17.15#debounce)

### ⚠️ Important Note

`maxWait` in Lodash implementation is renamed to `time_window` here, I think semantically it makes more sense.

## 🎉 Demo

See `demo.py` for a usage example.

## Requirements

- Python 3.9+
- asyncio library

## Contributing

Contributions are welcome. Please fork the repository and open a pull request.

## License

This project is released under the Apache-2.0 License. See the [LICENSE](./LICENSE) file for more details.
