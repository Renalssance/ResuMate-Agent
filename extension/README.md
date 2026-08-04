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
4. Open `extension/fixtures/application-form.html` in the browser.
5. Open the extension side panel.
6. Set backend URL and token.
7. Refresh profiles.
8. Scan page.
9. Confirm high-confidence fields are checked.
10. Click Fill Selected.
11. Verify normal fields are filled and the captcha field remains unchanged.
12. Verify the submit button was not clicked.
