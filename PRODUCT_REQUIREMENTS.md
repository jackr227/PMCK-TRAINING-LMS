# PMCK Training — Product Requirements (Non-Technical Presentation)

> **Purpose:** Define *what we want built* — the vision, features, roles, rules, flows, and outcomes — **without** prescribing any technology, frameworks, or implementation details.

---

## 1) Vision & Outcomes

**PMCK Training** is a single front door for multi-brand training and store operations.
It gives head office governance and store-level autonomy, so every person — from super admin to trainee — knows what to learn, by when, and how they’re doing.

**We want:**

* One platform for many brands (each with its own look, tone, logo).
* Global standards with local flexibility.
* Clear permissions (Discord-style) that match real-world hierarchy.
* Clean reporting that turns data into action.

---

## 2) Entry Experience (One Front Door)

* **Home page:** “PMCK Training” landing screen with a short platform intro and **Choose Your Brand** tiles.
* **Brand selection:** sets the user’s brand context and visual theme.
* **Login:** same login flow for everyone; access and content derive from the user’s role and store mappings.
* **Brand switcher:** always available to **Super Admin**. Admins are brand-scoped.

---

## 3) Roles & Hierarchy

**From highest to lowest:**
**Super Admin → Admin (Head Office) → Area Manager → Operator (Owner/GM) → Trainer → Trainee**

**Create/Remove powers (simple rules):**

* **Super Admin:** can create/remove **any** user in **any** brand.
* **Admin (brand):** can create/remove **Area Managers, Operators, Trainers, Trainees** **within** their brand.
* **Area Manager:** can **create** Operators/Trainers/Trainees for **their assigned stores** (no removals).
* **Operator:** can create/remove **Trainers & Trainees** for **their stores**.
* **Trainer:** can create/remove **Trainees** for **their stores**.
* **Trainee:** no user management powers.

> Everyone except Admin/Super Admin can be assigned coursework by default (unless explicitly included).

---

## 4) Brands, Stores, Areas

* **Brands:** visual identity (colors, fonts, logo, tone) applies across all screens and certificates.
* **Stores:** belong to a brand; have name, code, and region/province.
* **Store scoping:** Operators/Trainers only see and manage their own stores; Area Managers see multiple stores in their area.
* **Management:** Super Admin and Admin can create/edit/delete stores and map users to stores; Area Managers are mapped to their store set.

---

## 5) Users & Onboarding (No Public Sign-Up)

* **No public self-registration.** Users are added by permitted roles (as above).
* **User profile data (for certificates & comms):** First Name, Last Name, ID Number, Phone, Email (plus a display name).
* **Store memberships:** users can belong to one or many stores; each membership has a role (operator/trainer/trainee) and a status.
* **Approvals:** new memberships can start **pending**; **Operators/Trainers** approve for their stores.
* **Flags (optional):** free-form tags like “Student” or “Kitchen” used for targeting audiences.
* **Soft disable:** deactivate an account without deleting historical records.

---

## 6) Courses & Content

### Two course types

* **Global course**

  * Created by **Super Admin** (cross-brand) or **Admin** (brand-wide).
  * Default audience: “everyone eligible in scope” (can include/exclude subgroups).
  * Used for standards, compliance, and brand-level training.

* **Local course**

  * Created by **Admin, Operator, or Trainer**.
  * Audience limited to what the creator can see (their brand and/or stores).
  * Used for store-specific SOPs, corrective actions, and local needs.

### Structure & certificates

* **Course → Modules → Lessons** (support rich content and quizzes).
* **Certificates** generated on completion using First/Last Name and ID Number, styled with the brand identity.

---

## 7) Audience Targeting (Discord-Style Builder)

A guided panel to define **who gets the course**:

* **Includes:** Brand(s), Store(s), Role(s), Flag(s), User(s).
* **Excludes:** Role(s), Store(s), User(s) — to carve out exceptions.
* **Required toggle** + optional **Due date**.
* **Preview**: show counts and a sample list before publishing.
* **Visibility clamp:** final audience is automatically restricted to the creator’s permitted scope (e.g., a Trainer cannot target outside their stores).

> Result: precise, auditable targeting for both global pushes and local actions.

---

## 8) Learning Experience

* **Catalog tabs:** All Courses / Assigned to Me / Required / Completed.
* **Course detail:** overview, modules, lessons; enroll and track progress.
* **Required courses:** clearly highlighted and prioritized.
* **Notifications (optional):** on publish and for overdue required items.

---

## 9) Reporting & Analytics

**Super Admin (cross-brand):**

* Totals across brands, coverage by brand/store, top/least-engaged courses, global trends, CSV exports.

**Admin (brand):**

* Brand-wide metrics; compare stores; required-course coverage; split by **Global vs Local**; CSV exports.

**Area Manager:**

* Assigned stores only; registrations, active users, required coverage, at-risk stores (threshold configurable); CSV exports.

**Operator / Trainer:**

* Store roster; individual progress; required coverage %; outstanding required items; quick nudges; CSV exports.

**Key KPIs (examples):**

* Registrations, active users, enrollments
* Course completion %, required coverage %
* Top/least enrolled courses
* Overdue required items; stores under threshold

---

## 10) Governance & Guardrails

* **Role-based creation & removal** as defined above.
* **Edit/Delete:** a user can edit/delete courses within the same scope in which they can create them (plus ownership rules).
* **Brand scoping:** Admin actions confined to their brand; Area/Operator/Trainer confined to mapped stores.
* **Audit trail:** record who created/edited/published courses and who was targeted.
* **Privacy:** handle ID numbers and contact details responsibly; limit exposure to what a role needs to see.

---

## 11) Navigation & Information Architecture

* **Home:** PMCK Training overview + brand grid + login.
* **Brand Home:** greeting, quick links based on role:

  * Dashboard, Courses, **Create Course** (if allowed), **Assignments** (admin-level), **Reports** (if allowed), **Approvals** (operator/trainer), **Stores** (admin+), **Users** (as allowed).
* **Course creator wizard:**

  1. Basics (title, summary, cover, certificate style)
  2. Scope & Audience (Global/Local, includes/excludes, preview)
  3. Requirements & Publish (required toggle, due date, notify)
* **Search & filters:** by course type (Global/Local), tags/flags, required status, creator, store.

---

## 12) Accessibility, Reliability, Compliance (Targets)

* **Accessibility:** inclusive UI, readable typography, keyboard navigable.
* **Security:** least-privilege access; protect personal data.
* **Auditability:** actions and assignments traceable.
* **Reliability & scale:** support many brands and stores smoothly.
* **Observability:** meaningful logs and basic usage metrics.

---

## 13) Success Criteria

* Single entry point with brand-correct theming.
* Head Office can launch **Global** courses in minutes (brand-wide or cross-brand).
* Store leaders can create **Local** courses and assign within their scope.
* **Required coverage** and **at-risk** views drive action for Area Managers and Operators.
* Certificates include correct names and ID numbers with brand identity.
* CSV exports available for all key reports.
* No cross-store data leakage; permissions always respected.

---

## 14) Phased Rollout (Suggested)

1. **MVP:** Home + brand selection; login; brands & stores management; user creation; local course creation; assignments; learning; basic reports.
2. **Global Courses:** global audience builder, required toggle, due dates, notifications; coverage dashboards.
3. **Refinements:** audience preview & exclusions, flags, CSV everywhere, certificate layouts, audit reports.
4. **Scale:** course templates, cloning across brands, multilingual content, SSO options.

---

## 15) Open Questions (For the Delivery Team)

* Certificate layout standards per brand (logos, signatures, watermarks)?
* Notification channels and cadence (email/SMS, reminders, escalations)?
* Minimum user data at creation (are ID and phone always mandatory)?
* “At-risk” threshold defaults (e.g., <80% required coverage)?
* Should Area Managers also be able to create **Local** courses, or remain report-only?
* Delegation: can Admins temporarily grant operators edit rights on an Admin-authored local course?
* Multilingual and content approval workflow needs?

---

### One-Line Summary

A single PMCK Training front door for all brands, with brand-aware theming, Discord-style permissions, **Global vs Local** courses, precise audience targeting, certificate-ready data, and actionable reporting — expressed as **requirements**, not implementation.

