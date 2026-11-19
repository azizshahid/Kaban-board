# Board MCP server (read-only)

Lets Claude **read** your Productivity Board (tasks, deadlines, delay history, weekly plans) so the
board stays the single source of truth. There are **no write tools**: every request it makes is one
read of `GET /api/export`, it never asks for your notes, and it only talks to `127.0.0.1`.

| Tool | What it returns |
|---|---|
| `list_tasks(label, status, due_before)` | Tasks, filtered by label (ignoring case), status (`todo`/`progress`/`done`) and "due strictly before" a date |
| `overdue()` | Open tasks past their due date or time, most late first, with `daysLate` and `delayCount` |
| `week_plan(start_date)` | 7 days from `start_date` (default today): open tasks, time blocks, commitment deadlines, completed, delayed-from-this-day, estimate totals, overdue carry-over, In Progress count against the limit of 3, tasks delayed twice or more |
| `commitments_due(days)` | Open tasks whose commitment deadline is within `days` (0 to 365), including passed ones, with `daysLeft` and `deadlineLocked` |
| `delay_history(task_id)` | Every reschedule of a task (planned for, moved to, rescheduled on). Works for deleted tasks too |

## Install (Ubuntu)

```bash
cd ~/Desktop/Kaban-board
source .venv-linux/bin/activate
pip install -r mcp/requirements.txt
```

The board must be running (`./start-board.sh`) whenever Claude uses these tools. If it is not,
the tools answer with a clear "Cannot read the board ... Start it with ./start-board.sh" message.

Run the script **by path**, as in the commands below, not with `python -m`.

## Register with Claude Code

Use absolute paths (replace them with yours):

```bash
claude mcp add board -- /home/aziz_shahid/Desktop/Kaban-board/.venv-linux/bin/python /home/aziz_shahid/Desktop/Kaban-board/mcp/board_server.py
claude mcp list
claude mcp get board
```

`claude mcp list` should show `board` as connected (inside a Claude Code session, `/mcp` shows the same).
Everything after the `--` is the command that starts the server; any Claude Code options such as
`--scope` go before the name.

Scopes: the default, **local**, makes it available only in the project folder you ran the command in
and keeps it private to you. `--scope user` makes it available in every project. Avoid
`--scope project`: it writes a `.mcp.json` into the repo with paths that only work on your machine
(`.mcp.json` is in `.gitignore` for that reason).

To remove it: `claude mcp remove board`.

## Register with Claude Desktop

Edit `claude_desktop_config.json`:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux (if you run a Desktop build): `~/.config/Claude/claude_desktop_config.json`

In the app you can also use Settings, then Developer, then Edit Config.

```json
{
  "mcpServers": {
    "board": {
      "command": "/home/aziz_shahid/Desktop/Kaban-board/.venv-linux/bin/python",
      "args": ["/home/aziz_shahid/Desktop/Kaban-board/mcp/board_server.py"]
    }
  }
}
```

Use absolute paths (Desktop starts the command with a minimal environment), keep the JSON valid
(no trailing commas), and fully quit and reopen Claude Desktop after saving. On Windows, point
`command` at the virtual environment's `Scripts\python.exe` that has `mcp` installed and escape
backslashes in JSON (`C:\\Users\\...`).

## Safety

- No write tools, no tokens, no secrets in the repo.
- Only `127.0.0.1` / `localhost` is accepted for `BOARD_URL` (the default is `http://127.0.0.1:5000`).
- Notes are never requested, so Claude cannot read them through this server.
- Nothing is printed to stdout except protocol messages; diagnostics go to stderr.
