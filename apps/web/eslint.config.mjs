import next from "eslint-config-next";

/** ESLint flat config for the Next.js app (Next + core-web-vitals + TS rules). */
export default [
  ...next,
  {
    rules: {
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
  { ignores: [".next/**", "node_modules/**"] },
];
