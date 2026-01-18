export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // Allowed commit types
    'type-enum': [2, 'always', [
      'feat',     // New feature (MINOR bump)
      'fix',      // Bug fix (PATCH bump)
      'docs',     // Documentation only
      'style',    // Formatting, white-space
      'refactor', // Code restructure without feature/fix
      'perf',     // Performance improvement
      'test',     // Adding/fixing tests
      'build',    // Build system or dependencies
      'ci',       // CI configuration
      'chore',    // Maintenance tasks
      'revert',   // Revert a previous commit
    ]],
    // Scope must be lowercase
    'scope-case': [2, 'always', 'lower-case'],
    // Subject cannot be empty
    'subject-empty': [2, 'never'],
    // Type cannot be empty
    'type-empty': [2, 'never'],
    // Subject max length
    'subject-max-length': [2, 'always', 100],
    // Header max length
    'header-max-length': [2, 'always', 100],
  },
};
