# Product Understanding and User Journey

## Understand Before Judging

Before commenting on layout or visual style, establish:

- What the product helps users accomplish and who the primary users are.
- Their most important task, entry point, and expected outcome.
- How the relevant pages, navigation, and existing design patterns fit together.
- Which areas changed recently, when that information is available.

Use the README, product documentation, visible UI, routes, navigation, tests, and relevant recent changes as evidence. Read source to clarify behavior, not as a substitute for observing a runnable UI. Keep discovery proportional to the requested scope.

## Review the Workflow First

Map the user-visible steps from entry to outcome. Look for unnecessary page changes, lost context, repeated data entry, unclear next actions, dead ends, and poor recovery after errors. For tool and admin products, examine how users move between creating or editing, running an action, observing results, and correcting problems.

Do not assume each capability needs a separate page or that putting everything on one screen is always better. Judge the structure by task continuity and the user's mental model.

## Select the Golden Journey

Choose the end-to-end path that best represents the product's core user value. Infer it from the user's request, documentation, navigation, routes, tests, primary actions, and visible product. Prefer the real value chain over the easiest page to inspect. Record its concrete steps and outcome; identify points that could not be observed.

For a request covering many pages or features, make a coverage matrix with page/feature, user goal, primary action, result, evidence, and unverified areas. Prioritize:

- **P0:** core value journey.
- **P1:** frequent, major capabilities.
- **P2:** secondary tasks.
- **P3:** auxiliary areas.

Do not claim comprehensive coverage unless the requested matrix was actually reviewed.
