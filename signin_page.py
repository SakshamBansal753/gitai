# signin_page.py
"""
Builds the local sign-in HTML page using Clerk's official <SignIn /> prebuilt
component, loaded via the CDN <script> tag method.
Supports multi-user authentication, confirmation, and account switching.
"""

SIGNIN_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>GitAI Sign In</title>
  <style>
    body {{
      font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      margin: 0;
      background: #0d1117;
      color: #c9d1d9;
    }}
    #app {{
      text-align: center;
      max-width: 440px;
      width: 100%;
      padding: 32px;
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 12px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
    }}
    h2 {{
      margin-top: 0;
      margin-bottom: 8px;
      color: #58a6ff;
    }}
    p.subtitle {{
      color: #8b949e;
      font-size: 14px;
      margin-top: 0;
      margin-bottom: 24px;
    }}
    .user-card {{
      background: #21262d;
      border: 1px solid #30363d;
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 20px;
      display: flex;
      align-items: center;
      gap: 12px;
      text-align: left;
    }}
    .avatar {{
      width: 44px;
      height: 44px;
      border-radius: 50%;
      background: #30363d;
      object-fit: cover;
    }}
    .user-info {{
      flex: 1;
      overflow: hidden;
    }}
    .user-name {{
      font-weight: 600;
      color: #f0f6fc;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .user-email {{
      font-size: 12px;
      color: #8b949e;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .btn {{
      display: block;
      width: 100%;
      padding: 10px 16px;
      border-radius: 6px;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      border: none;
      box-sizing: border-box;
      margin-top: 10px;
      transition: background 0.15s;
    }}
    .btn-primary {{
      background: #238636;
      color: #ffffff;
    }}
    .btn-primary:hover {{
      background: #2ea043;
    }}
    .btn-secondary {{
      background: #21262d;
      color: #c9d1d9;
      border: 1px solid #30363d;
    }}
    .btn-secondary:hover {{
      background: #30363d;
    }}
    #status {{
      margin-top: 16px;
      font-size: 13px;
      color: #8b949e;
    }}
  </style>
</head>
<body>
  <div id="app">
    <h2>GitAI Sign In</h2>
    <p class="subtitle">Authenticate with your GitHub account for this CLI session.</p>
    
    <div id="user-prompt" style="display: none;">
      <div class="user-card">
        <img id="avatar-img" class="avatar" src="" alt="avatar" />
        <div class="user-info">
          <div id="user-display-name" class="user-name"></div>
          <div id="user-display-email" class="user-email"></div>
        </div>
      </div>
      <button class="btn btn-primary" onclick="confirmCurrentAccount()">Continue as this user</button>
      <button class="btn btn-secondary" onclick="switchAccount()">Sign in with different account</button>
    </div>

    <div id="sign-in"></div>
    <div id="status"></div>
  </div>

  <script
    defer
    crossorigin="anonymous"
    src="https://{frontend_api}/npm/@clerk/ui@1/dist/ui.browser.js"
    type="text/javascript"
  ></script>

  <script
    defer
    crossorigin="anonymous"
    data-clerk-publishable-key="{publishable_key}"
    src="https://{frontend_api}/npm/@clerk/clerk-js@6/dist/clerk.browser.js"
    type="text/javascript"
  ></script>

  <script>
    window.addEventListener('load', async function () {{
      await Clerk.load({{
        ui: {{ ClerkUI: window.__internal_ClerkUICtor }},
      }});

      if (Clerk.isSignedIn) {{
        showUserConfirmation();
      }} else {{
        renderSignInForm();
      }}
    }});

    function showUserConfirmation() {{
      const user = Clerk.user;
      const name = user.fullName || user.username || 'User';
      const email = user.primaryEmailAddress ? user.primaryEmailAddress.emailAddress : '';
      const avatar = user.imageUrl || '';

      document.getElementById('user-display-name').innerText = name;
      document.getElementById('user-display-email').innerText = email;
      if (avatar) {{
        document.getElementById('avatar-img').src = avatar;
        document.getElementById('avatar-img').style.display = 'block';
      }} else {{
        document.getElementById('avatar-img').style.display = 'none';
      }}

      document.getElementById('user-prompt').style.display = 'block';
      document.getElementById('sign-in').style.display = 'none';
    }}

    function renderSignInForm() {{
      document.getElementById('user-prompt').style.display = 'none';
      const signInDiv = document.getElementById('sign-in');
      signInDiv.style.display = 'block';
      Clerk.mountSignIn(signInDiv);

      const interval = setInterval(async () => {{
        if (Clerk.isSignedIn) {{
          clearInterval(interval);
          await notifyServer();
        }}
      }}, 1000);
    }}

    async function confirmCurrentAccount() {{
      await notifyServer();
    }}

    async function switchAccount() {{
      document.getElementById('status').innerText = 'Signing out previous account...';
      await Clerk.signOut();
      document.getElementById('status').innerText = '';
      renderSignInForm();
    }}

    async function notifyServer() {{
      document.getElementById('user-prompt').style.display = 'none';
      document.getElementById('sign-in').style.display = 'none';
      document.getElementById('status').innerHTML =
        '<div style="color:#58a6ff; margin-bottom:12px;">Saving & verifying in database...</div>';

      const sessionId = Clerk.session.id;
      await fetch('/capture?session_id=' + encodeURIComponent(sessionId));

      const user = Clerk.user;
      const username = user.username || user.firstName || 'user';
      document.getElementById('app').innerHTML =
        '<h2 style="color:#3fb950; margin-bottom: 8px;">GitAI Login Complete</h2>' +
        '<p style="color:#8b949e">Signed in as <b>' + username + '</b>.</p>' +
        '<p style="color:#58a6ff; font-size: 13px;">Details verified in database. You can return to your terminal.</p>';
    }}
  </script>
</body>
</html>
"""


def build_signin_html(publishable_key: str, frontend_api: str) -> str:
    return SIGNIN_HTML_TEMPLATE.format(
        publishable_key=publishable_key,
        frontend_api=frontend_api,
    )
