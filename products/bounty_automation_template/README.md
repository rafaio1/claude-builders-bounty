# Bounty Automation Template
Automated bounty triage engine with schema validation and regression tests.

## Contents
- `bounty_engine.py`: Core triage engine with JSON extraction, unicode normalization, and schema validation
- `tests/`: 12 pytest regression tests covering contract compliance

## Requirements
- Python 3.10+
- pytest

## Usage
```bash
pip install pytest requests
pytest tests/ -v
python bounty_engine.py --help
```

## License
MIT - Free for commercial and personal use.

## Support
Issues and PRs welcome. No guaranteed response time.
