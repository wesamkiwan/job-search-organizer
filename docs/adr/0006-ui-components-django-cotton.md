# ADR 0006: UI components with django-cotton

- **Status:** Accepted
- **Date:** 2026-11-24

## Context
The UI is server-rendered Django templates styled with Tailwind (see the architecture
document). Buttons, cards, badges, tables, form fields, modals and empty states repeat on
every page. If they are copied, every design change has to be made in many places and the
look drifts apart. Options considered:

- **`{% include %}` with parameters**: built in, but awkward for content inside a component
  (`{% include "button.html" with label="Save" %}`, no nested markup) and every template
  variable leaks into the included file.
- **Custom inclusion tags** (`@register.inclusion_tag`): explicit, but a Python function
  plus a template per component, and still no nested content.
- **django-components**: powerful (Python classes, JS/CSS per component), but much more
  machinery than this project needs.
- **django-cotton**: components are plain template files used like HTML tags, with slots
  for nested content: `<c-button variant="secondary">Cancel</c-button>`.

## Decision
Use django-cotton (2.9) for UI components, stored in `templates/components/`
(`COTTON_DIR = "components"`).

- Configured **explicitly** in `TEMPLATES` (`SimpleAppConfig`, own `loaders` and `builtins`)
  instead of letting the package rewrite the settings at startup.
- `COTTON_ISOLATE_BY_DEFAULT = True`: a component only sees the attributes passed to it
  (plus context processors such as `request`), like a function with explicit arguments.
- Each component documents its parameters in a comment at the top of its file.
- A development-only gallery at `/ui/` shows every component for visual checks in light and
  dark mode.

## Consequences
- Templates read like HTML, which works well with Tailwind classes and HTMX/Alpine attributes
  (`{{ attrs }}` passes unknown attributes through to the element).
- Design changes happen in one file per component.
- One more dependency, and a template loader that compiles `<c-...>` tags before Django
  parses them. Errors in component templates can be slightly less direct to trace.
- Components are templates, not Python: complex logic stays in views/selectors, which is
  the intended split anyway.
