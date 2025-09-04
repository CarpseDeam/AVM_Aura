# Gemini Code Assist Integration

This document outlines the role and conventions of Gemini Code Assist (referred to as Gemini) within the AURA project. Gemini acts as an AI-powered pair programmer and software engineering assistant.

## Gemini's Role

Gemini's primary objective is to enhance developer productivity and improve code quality. Its responsibilities include:

- **Answering Questions**: Providing insightful answers about the codebase, architecture, and best practices.
- **Code Implementation**: Writing new features, fixing bugs, and implementing functionality based on developer requests.
- **Code Review & Refactoring**: Analyzing existing code to identify areas for improvement, suggesting refactors, and enhancing clarity, performance, and maintainability.
- **Documentation**: Assisting with the creation and maintenance of project documentation.
- **Troubleshooting**: Diagnosing issues, analyzing logs, and proposing solutions to complex problems.

## Interaction Model

Interaction with Gemini is conversational. Developers can make requests in natural language (e.g., "@Gemini, can you refactor this function to be more efficient?").

Gemini will respond with:
1.  A clear explanation of the proposed changes.
2.  Code diffs in the unified format, showing the exact modifications.
3.  A well-formed `git` commit message that summarizes the changes.

## Conventions

To ensure consistency and maintain a clean project history, Gemini adheres to the following conventions:

### 1. Code Changes

All code modifications are provided in a `diff` format with full file paths. This allows for easy review and application of the changes.

### 2. Commit Messages

Every code change is accompanied by a descriptive commit message following the Conventional Commits specification. This practice helps create an explicit and easily navigable commit history.

A typical commit message looks like this:

```
feat(gui): Add user profile editing feature

- Implements the UI for the user profile page.
- Adds backend logic to handle profile updates.
- Includes validation for user input fields.
```