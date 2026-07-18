# Interface selection and recovery

| Field | Value |
| --- | --- |
| Source branch | `v1-runtime-hardening` |
| Intended target | `main` |
| Status | Implemented, pending hardware qualification |
| Owner | Desktop shell runtime |

## Problem

Open MMI can remember either the Web Dashboard or the Terminal UI as its default interface. On a preinstalled touchscreen system, remembering the Terminal UI must not make the Web Dashboard unreachable without typing terminal commands.

The desktop-shell checkpoint exposed three recovery risks:

- the main launcher silently used the remembered interface;
- the desktop chooser action persisted every selection immediately;
- closing a graphical TUI terminal could leave the user without an obvious route back to the Web Dashboard.

## Goals

- A touchscreen-only user can always return from the Terminal UI to the Web Dashboard.
- Selecting an interface once does not persist unless the user explicitly confirms it.
- A permanent application-menu entry opens the interface chooser regardless of the saved default.
- Closing or failing the graphical TUI opens the chooser instead of leaving an empty terminal or desktop.
- A missing or cancelled graphical chooser falls back to the Web Dashboard for the current session.
- Explicit CLI choices remain available for administrators and scripted deployments.

## Behaviour

### Normal launcher

`open-mmi-launcher` continues to open the remembered default interface.

Explicit commands remain deterministic:

```text
open-mmi-launcher web
open-mmi-launcher tui
open-mmi-launcher web --remember
open-mmi-launcher tui --remember
```

Without `--remember`, an explicit choice applies only to the current launch.

### Interactive chooser

The application-menu entry **Open MMI Interface Chooser** runs:

```text
open-mmi-launcher --choose --ask-remember
```

The chooser first selects Web Dashboard or Terminal UI, then asks whether the selection should become the default. Declining the confirmation launches the selected interface once without changing `launcher.json`.

The primary Open MMI desktop entry exposes the same chooser through its desktop action. Explicit Web and TUI desktop actions continue to set the chosen interface as the default because their labels describe a persistent choice.

### Terminal UI guardian

When the TUI is launched from a graphical session, the launcher waits for the terminal window to close. It then opens the interface chooser.

- Choosing Web Dashboard starts or verifies the dashboard service and opens the managed browser.
- Choosing Terminal UI starts another guarded TUI session.
- Confirming the remember prompt updates the shared launcher preference.
- Cancelling the chooser or lacking Zenity/Yad opens the Web Dashboard for the current session so the user is not stranded.

When the TUI is launched in a non-graphical interactive terminal, normal terminal behaviour is preserved.

### Terminal emulator lifecycle

Known terminal emulators are started with their wait/no-fork option so the guardian can detect when the TUI window closes:

- GNOME Terminal: `--wait`
- MATE Terminal: `--disable-factory`
- XFCE Terminal: `--disable-server`
- Konsole: `--nofork`
- Other compatible terminals: `-e`

## Installation

The installer manages two application-menu entries:

```text
~/.local/share/applications/open-mmi.desktop
~/.local/share/applications/open-mmi-chooser.desktop
```

Only the main Open MMI entry is copied to the literal desktop. The recovery chooser remains an independent application-menu entry and is removed during uninstall.

## Failure handling

- A TUI launch failure enters the same recovery flow as a normal TUI exit.
- A cancelled graphical recovery chooser opens Web Dashboard once.
- A missing graphical chooser opens Web Dashboard once and reports the fallback on standard error.
- A missing terminal emulator remains a visible launcher error; the independent chooser entry still provides a Web Dashboard route.
- The recovery flow never disables services, deletes configuration, or changes the default without confirmation.

## Tests

Automated coverage must verify:

- chooser selection and remember confirmation are separate;
- `--ask-remember` is valid only with `--choose`;
- the standalone chooser entry ignores the saved default;
- installer/update/uninstall manage both application-menu entries;
- the graphical TUI launcher waits for the terminal lifecycle;
- closing the TUI can recover to Web Dashboard;
- selecting TUI again retains the guardian loop;
- cancelling recovery falls back to Web Dashboard;
- explicit `web --remember` and `tui --remember` behaviour remains unchanged.

## Qualification

Before merge, verify on the target Surface Pro using touch only:

1. Set Terminal UI as the remembered default.
2. Launch Open MMI and confirm the TUI opens.
3. Close the TUI terminal using the window controls.
4. Confirm the graphical chooser appears.
5. Select Web Dashboard and remember it.
6. Confirm Chromium opens and the next normal Open MMI launch goes directly to Web Dashboard.
7. Repeat using **Open MMI Interface Chooser** from the application menu.
