# Visual and Interaction Review

Review visual quality in service of usability. Respect the product's category, brand, platform conventions, and existing design system; inspect tokens, shared layouts, and reusable components before proposing a visual change. Do not create a second button, dialog, spacing scale, or typography system when an appropriate shared pattern exists.

## Visual and Component Dimensions

Check relevant areas for:

- **Hierarchy:** page purpose, headings, primary and secondary actions, and information grouping.
- **Layout:** spacing, alignment, density, line length, overflow, clipping, panel width, and scroll behavior.
- **Typography:** readable sizes, consistent heading levels, clear labels, and adequate contrast.
- **Consistency:** buttons, inputs, selects, dialogs, drawers, cards, tables, tabs, tooltips, toasts, badges, and navigation use coherent semantics and interaction.
- **Discoverability:** users can find primary actions; menus and icon-only controls are understandable.

Do not impose a fixed aesthetic. Avoid decorative redesigns that add cards, gradients, shadows, glass effects, or icons without improving comprehension or task completion. Do not reduce useful information density or hide important actions for visual simplicity.

## States and Feedback

For actions in scope, review:

- **Loading:** progress or system activity is clear, including for long-running tasks.
- **Empty:** the state explains what is absent and gives a useful next step.
- **Error:** the failure and recovery path are understandable; retry is offered only when it is safe.
- **Success:** completion and its result are visible.
- **Disabled:** users can understand why an action is unavailable when that matters.

Check whether interaction feedback preserves context and makes the next step clear. Loading text alone is weak when the user cannot tell whether work is progressing or stuck.
