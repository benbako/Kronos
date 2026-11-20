# Journal for Kronos web UI

Standalone trade journal + profit/loss dashboard for the Kronos Flask web UI.
No Base44, no external services — trades are stored in a local SQLite file.

## Install

1. Copy the `journal` folder into `webui/`, next to `app.py`.
2. In `webui/app.py`, register it:

```python
from journal import journal_bp
app.register_blueprint(journal_bp)
```

3. Add a link in your nav / any template:

```html
<a href="{{ url_for('journal.index') }}">Journal</a>
```

4. Start the app as usual (`python app.py`) and open http://localhost:7070/journal

Trades are saved in `webui/journal.db` (created automatically on first import).
Add `journal.db` to your `.gitignore` so local trades never get committed.

## Files

- `__init__.py` — exports `journal_bp`
- `routes.py` — SQLite storage, add / close / delete, profit & loss summary
- `templates/journal.html` — the dashboard and trade list
