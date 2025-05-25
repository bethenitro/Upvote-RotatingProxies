# RedditUpvote – Beginner-Friendly Guide

Welcome to **RedditUpvote**, a simple tool that automates upvoting Reddit posts using multiple accounts. This guide is designed for **absolute beginners** — no coding experience needed!

---

## 📋 What You’ll Need

Before starting, make sure you have:

* ✅ A **Windows PC**
* ✅ **Python 3.11.3** installed
* ✅ A working **internet connection**
* ✅ **Reddit accounts**
* ✅ *(Optional)* **Proxy details** (for safer and more anonymous usage)

---

## 🛠️ Step-by-Step Setup

### 1. Clone the Project

1. Open **PowerShell**
2. Run this command to download RedditUpvote:

```powershell
git clone https://github.com/bethenitro/Upvote-RotatingProxies.git
cd Upvote-RotatingProxies
```

> ❗ Don’t have Git installed? Just Google: *“how to install Git on Windows”* and follow the steps.

---

### 2. Create Required Files & Folders

#### ➤ Create `account_state.json`:

```powershell
New-Item account_state.json -ItemType File
```

> Make sure you’re inside the `RedditUpvote` folder before running this.

#### ➤ Create the `profiles` folder:

```powershell
New-Item -ItemType Directory -Name profiles
```

This folder will store login session data for your Reddit accounts.

---

### 3. Set Up the Python Environment

#### ➤ Create a virtual environment:

```powershell
python -m venv env
```

#### ➤ Activate the virtual environment:

```powershell
.\env\Scripts\activate
```

> You’ll now see `(env)` before your prompt — this means the environment is active.

---

### 4. Install Project Dependencies

Install all required Python packages:

```powershell
pip install -r requirements.txt
```

---

## 👤 Adding Reddit Accounts

To let the bot log in with your Reddit accounts:

1. In PowerShell, run:

```powershell
python account_gui.py
```

2. A window will open. Click **"Add Account"**, then fill in:

* **Account ID** (a name to identify the account)
* **Proxy (optional)** – If you're using rotating proxies, **leave this blank** (they are configured later)
* **Username**

3. The bot will open Reddit, scroll, simulate natural activity, and close.

4. Click **"Exit & Save"** to finish.

> 🔁 Repeat this for each account you want to add.

---

## 🔄 Rotating Proxies 

Using rotating proxies keeps your accounts safe and reduces the chance of getting blocked.

### Step 1: Create a `mobile_proxies.json` File

In the **main folder**, create a file named:

```
mobile_proxies.json
```

Then open it and paste this example structure:

```json
[
  {
    "server": "proxy1.server:port",
    "username": "proxy1_username",
    "password": "proxy1_password",
    "rotation_url": "https://your-proxy-rotation-url-1"
  },
  {
    "server": "proxy2.server:port",
    "username": "proxy2_username",
    "password": "proxy2_password",
    "rotation_url": "https://your-proxy-rotation-url-2"
  }
]
```

### What Each Field Means:

| Field          | Description                                                               |
| -------------- | ------------------------------------------------------------------------- |
| `server`       | The proxy address and port (e.g. `104.248.168.156:8019`)                  |
| `username`     | Your proxy account username                                               |
| `password`     | Your proxy account password                                               |
| `rotation_url` | A special link your proxy provider gives you to **change the IP address** |

> ✅ Make sure your proxy provider supports IP rotation through a URL.

---


## 🎯 Upvoting a Reddit Post

After setting up accounts and (optionally) proxies, here’s how to run the bot:

1. In PowerShell, run:

```powershell
python target_gui.py
```

2. A window will open. Click **“New Instance”**

3. Fill in:

* The **Reddit post URL** you want to upvote
* Optional settings like **upvote delay** or **account filtering**

4. Click **“Start Upvoting”**

The bot will:

* Open Reddit using each account
* Log in, scroll, simulate browsing
* Upvote the post
* Close the browser window

> 🔁 This process is repeated for each account, and rotating proxies are used automatically if configured.

---

## 📝 Notes

* ⚠️ The **first time** you run `account_gui.py`, it may take extra time — it's setting up everything.
* 🚫 If you don’t have proxy info, just leave the field blank when adding accounts.
* 🌐 Proxies are configured globally using `mobile_proxies.json`, not per account.

---

## 💬 Need Help?

If you have any questions or run into issues, feel free to [open an issue on GitHub](https://github.com/bethenitro/Upvote-RotatingProxies/issues) or check Reddit automation communities for help.

---

Happy upvoting! 🚀
