# Terminal design contract

Reference: https://yannglt.com/writing/designing-for-command-line-interface

The design follows the reference's actual terminal components: thin horizontal
header rules, a two-line product/model/workspace header, character-based spacing,
bold task names, dim secondary information, and ANSI background labels for INFO,
PROCESSING, SUCCEEDED, WARNING and FAILED. Nested execution rows carry the tool
name and real checkpoint status. The Figma selection frames and macOS window
controls in the source screenshot are not application components.

The default view is a persistent task prompt in scrollback. It does not repaint
an alternate screen or print a dashboard of fictional statistics. Arrow-key
history, inline validation and searchable completion use prompt-toolkit. Ctrl-P
opens command selection with descriptions; agent and task IDs complete from the
active workspace. History stays in memory. Task records,
tool discovery, agent selection, approval and recovery are reachable from the
same session. No browser or HTML output is part of the product.

Rich handles display cell widths, wrapping, ANSI capability and spinner cleanup.
All dynamic text is passed as literal Text, never evaluated as Rich markup.
Control sequences and bidirectional overrides are removed from tool/model text.
The terminal owns its font and background; Pi does not force a dark theme.

Animation represents activity only. No percentage is displayed for unknown work.
Version 0.4 uses a single Rich Live surface during work, with cyan activity,
green success, coral failure and yellow review badges. Task IDs distinguish
parallel agents; the view follows real checkpoint/model/tool events and freezes
into scrollback on completion or interruption. Workflow progress counts completed
nodes against the validated DAG size, not guessed model completion percentages.
Plain mode and NO_COLOR preserve textual status names without relying on color.
Piped JSON has no styling or progress. The UI is tested at 32, 40, 80, 120 and
180 columns; terminal font and custom ANSI palettes can change perceived colors.

Approval shows exact arguments, a local file diff where applicable, and the
action hash. A receipt indicates its verification scope. Model completion,
remote tool response and verified local readback are distinct concepts.

`/review` opens the newest pending action. Completion never inserts an approval
hash or submits an approval. All existing exact-hash authority checks remain in
the engine. The presentation's state is ephemeral and never drives execution.

Verification includes real local approval/write rendering, truecolor and
monochrome tests, 32/40/80/120-column live output, parallel task identities,
failed-check labels, interruption cleanup, and interactive PTY command selection.
`tests/render_terminal.py` exports actual local fixture receipts as SVGs for
visual inspection; these are test artifacts, not a product demo mode.

The previous component-gallery and ticket-dashboard renderer remains only in
the archived teaching CLI. It is not shipped by the Python package.
