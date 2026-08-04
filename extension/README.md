# ResuMate Autofill Extension

## Load Locally

1. Open Chrome or Edge.
2. Go to `chrome://extensions`.
3. Enable Developer mode.
4. Choose "Load unpacked".
5. Select the `extension/` directory.
6. Open a recruiting application page and click the ResuMate Autofill toolbar icon.

## First Version Boundary

- The extension fills selected fields only after user review.
- It does not submit applications.
- It does not bypass login, captcha, two-factor checks, or site restrictions.
- File upload fields are shown as manual actions.

## Manual Verification

1. Start ResuMate backend at `http://127.0.0.1:8000`.
2. Log in through the main app and copy the JWT from local storage, or call `/auth/login` and copy `access_token`.
3. Load the unpacked extension.
4. From the repo root, run `python -m http.server 8899`.
5. Open `http://127.0.0.1:8899/extension/fixtures/application-form.html` in the browser.
6. Open the extension side panel.
7. Set backend URL and token.
8. Refresh profiles.
9. Scan page.
10. Confirm high-confidence fields are checked.
11. Click Fill Selected.
12. Verify normal fields are filled and the captcha field remains unchanged.
13. Verify the submit button was not clicked.
