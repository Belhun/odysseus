# Toast notifications

## What it does in SysForge

Transient user feedback; error messages with optional clipboard copy.

**Paths**

- `SysForge/Services/ToastService.cs`
- Used throughout ViewModels (e.g. `MainWindowViewModel`)

## Status

**Done**

## Dependencies

- Avalonia UI thread dispatch

## Port approach

Lightweight JS toast module scoped to `.sysforge-panel`, or reuse Odysseus notification patterns if compatible. No backend.

## Effort

**S**

## Risks / open questions

- Global Odysseus toasts vs scoped Business toasts — prefer scoped
