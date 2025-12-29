# AppFlowy-SelfHost-Commercial

> The commercial fork is distributed solely under the [AppFlowy Self-Hosted Commercial License](https://github.com/AppFlowy-IO/AppFlowy-SelfHost-Commercial/blob/main/SELF_HOST_LICENSE_AGREEMENT.md)

---

## Release

### 🚀 v0.10.1 (Latest)

#### Features

- Added AI Meeting feature for intelligent meeting assistance
  - **Requires:** Set the `ASSEMBLYAI_API_KEY` environment variable. [Get your API key here](https://www.assemblyai.com/docs/faq/how-to-get-your-api-key)
- Enhanced Web API with improved database creation capabilities

#### Improvements

- Improved performance by caching user and member profiles in Redis

### 🚀 v0.9.159

#### Improvements

- Optimized the Publish Page for faster loading and smoother performance
- Made file and image URLs private across the app, with access allowed only on the Publish Page

#### Bug Fixes

- Fixed an issue in the join-by-invite-code flow where an already-seated Member/Owner was incorrectly counted again. The system now properly avoids consuming an extra seat

#### Other Changes

- Deprecated the ws v1 API endpoint in preparation for future cleanup and migration