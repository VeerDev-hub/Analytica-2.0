// Project sections shown in the sidebar. Each page uses the same title + description.
export const PROJECT_SECTIONS = [
  { id: 'data', label: 'Data', icon: 'data', description: 'Browse every row of the current version. Click a column’s type badge to inspect it.' },
  { id: 'explore', label: 'Explore', icon: 'explore', description: 'Summary statistics, quality alerts with one-click fixes, column profiles and charts.' },
  { id: 'clean', label: 'Clean', icon: 'clean', description: 'Fix types, text, missing values, rows and columns. Preview every step on a sample before it runs.' },
  { id: 'features', label: 'Features', icon: 'features', description: 'Split into train/validation/test, then encode, scale, balance and select features for ML.' },
  { id: 'validate', label: 'Validate', icon: 'validate', description: 'Check the data is ready to train on and see how quick baseline models score.' },
  { id: 'export', label: 'Export', icon: 'export', description: 'Download the prepared data, the code that reproduces it, and model starter templates.' },
  { id: 'assistant', label: 'Assistant', icon: 'assistant', description: 'Ask questions in plain language. Every number comes from a query you can open and check.' },
];

export const sectionById = Object.fromEntries(PROJECT_SECTIONS.map((s) => [s.id, s]));

// Which page a step type is configured on.
export const FEATURE_STEPS = new Set([
  'split', 'one_hot', 'ordinal', 'label_encode', 'target_encode', 'frequency_encode', 'hash_encode',
  'scale', 'numeric_transform', 'feature_select', 'pca', 'smote', 'adasyn', 'random_over', 'random_under', 'tomek',
]);
export const pageForStep = (/** @type {string} */ stepType) => (FEATURE_STEPS.has(stepType) ? 'features' : 'clean');
