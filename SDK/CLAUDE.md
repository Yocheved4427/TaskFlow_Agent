# TaskFlow: project memory

Claude Code loads this file at the start of every session
(`setting_sources=["project"]`). It holds the standing rules; the user's own
rules, preferences and tasks live in the TaskFlow store, reached through tools.

- At the start of a session, or before adding or moving tasks, call `recall`
  to load the user's saved rules. They are not in your context otherwise.
- Save every new scheduling rule with `remember` (kind=rule).
- Tasks and holidays live in the TaskFlow tools. Do not read or write files.
