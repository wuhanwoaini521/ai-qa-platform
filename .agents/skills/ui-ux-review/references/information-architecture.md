# Information Architecture and Redundancy

Review the structure users must understand to find and complete tasks:

- Navigation groups, labels, hierarchy, and entry points.
- Page and workspace responsibilities, information ownership, and terminology.
- Repeated links, controls, settings, actions, result views, and concepts.
- Whether users can tell where they are and what to do next.

Classify suspected overlap as:

- **Duplicate:** the same capability or information is independently implemented more than once.
- **Redundant:** multiple controls or destinations expose substantially the same action without a clear user benefit.
- **Related but intentionally separate:** similar concepts serve distinct tasks, permissions, lifecycles, or users.

Verify behavior and context before calling something a duplicate. Explain the user cost, such as inconsistent results, uncertainty about the canonical action, or unnecessary navigation.

## Page Proliferation and Consolidation

Do not recommend a new page solely to make the menu or architecture appear modular. For tightly connected steps, consider keeping work in a shared workspace using a contextual panel, tab, drawer, side pane, or progressive disclosure. Recommend separate destinations when they represent distinct user goals, require a different working context, or have a meaningful access/lifecycle boundary.

Consolidation must preserve discoverability and primary actions. Progressive disclosure should move advanced or infrequent controls out of the way without hiding core tasks, status, or recovery paths.
