Every session once completing a good milestone should commit the code to the repo

## Application design

Read and follow [design.md](design.md) before creating or changing any UI. It is the
frozen design baseline for the application shell, tokens, icons, tables, forms,
responsive behavior, accessibility, and concise copy. Reuse the shared components
and CSS tokens; update design.md alongside any intentional design-system change.

Do not build the Docker without explicit instructions

## File organization

- Give each file a specific, descriptive name that accurately reflects its purpose.
- Keep files focused on one cohesive responsibility. When a file contains multiple
  distinct components or independent pieces of logic, split them into smaller,
  purpose-specific files rather than continuing to grow the combined file.
- Apply this rule when creating code and when changing an existing file with mixed
  responsibilities. Keep extraction relevant to the current task and preserve behavior.
- Keep closely related code together when separating it would only add indirection.
  Follow the project's existing directory structure and naming conventions.
