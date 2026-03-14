# Sync V2 Testing: The UX Reality of V3 Architectural Flaws

The `sync-v3-audit-findings.md` outlines theoretical problems with the backend Syncthing architecture. This document explains what those backend flaws actually do to the user.

## 1. The "Sync Now" Button is a Placebo

**The Architectural Flaw:** `BP-7` (Inconsistent Outbox Creation)
**The UX Impact:**
The user clicks "Sync Now". The frontend shows a success state. The backend packages the files. **But the files never leave the machine.** 
Because `ensure_outbox_folder` isn't consistently called, the transport layer is oblivious. The UI implies a successful sync when nothing has happened.

## 2. Cloned Projects are Arbitrarily Misassigned

**The Architectural Flaw:** `BP-1` & `BP-8` (Team-Agnostic Folders & Additive Pipeline)
**The UX Impact:**
The backend cannot figure out who a sync folder belongs to, so it guesses. 
If a user receives a clone of a project but hasn't mapped it to a local team yet, the UI arbitrarily assigns the "Pending Share" notification to the *first team it finds alphabetically* (e.g., `v2-team-1`). The user is presented with a notification under the wrong team dashboard, creating immediate trust issues with the permission model.

## 3. Remote Sessions Hard-Crash the Frontend

**The Architectural Flaw:** Unrelated to Syncthing (Pure Frontend/API Logic Bug)
**The UX Impact:** 
When viewing remote sessions for a project that doesn't exist locally, the entire page hard-crashes with a 404. The data exists in the local SQLite database, but the frontend router blindly checks the local filesystem for the project directory before loading it. 
*Note: Fixing the V3 sync architecture will not fix this. This is a separate UI bug that must be addressed.*