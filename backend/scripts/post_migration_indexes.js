/**
 * VHC Talent OS — MongoDB Index Migration
 *
 * Run this script BEFORE deploying the fixed application code.
 * All operations are additive (createIndex is idempotent).
 * No downtime required.
 *
 * Usage:
 *   mongosh "mongodb+srv://..." --file post_migration_indexes.js
 *
 * IMPORTANT: Run the dedup check below BEFORE adding the unique email
 * index. Adding a unique index on a collection with duplicate emails
 * will fail.
 */

// ── Switch to correct database ────────────────────────────────────────────
use("vhc_talent_os");

// ============================================================
// STEP 1: CHECK FOR DUPLICATE EMAILS (run before unique index)
// ============================================================
print("=== Checking for duplicate emails ===");
const dupEmails = db.candidate_bank.aggregate([
  { $match: { email: { $exists: true, $ne: null, $ne: "" } } },
  { $group: { _id: "$email", count: { $sum: 1 } } },
  { $match: { count: { $gt: 1 } } },
  { $sort:  { count: -1 } },
  { $limit: 20 },
]).toArray();

if (dupEmails.length > 0) {
  print("WARNING: Duplicate emails found. Resolve before adding unique index:");
  dupEmails.forEach(d => print(`  ${d._id}: ${d.count} documents`));
  print("Run the dedup resolution query below, then re-run this script.");
} else {
  print("No duplicate emails found. Safe to proceed.");
}

// ============================================================
// STEP 2: REQUIRED INDEXES (add immediately — no dedup needed)
// ============================================================

print("\n=== Creating required indexes ===");

// Skill search — both field names (covers historical + new documents)
db.candidate_bank.createIndex(
  { "key_skills": 1 },
  { name: "idx_key_skills", background: true }
);
print("Created: idx_key_skills");

db.candidate_bank.createIndex(
  { "skills": 1 },
  { name: "idx_skills", background: true }
);
print("Created: idx_skills");

// IT skills search
db.candidate_bank.createIndex(
  { "it_skills.name": 1 },
  { name: "idx_it_skills_name", background: true }
);
print("Created: idx_it_skills_name");

// Experience search — both field names
db.candidate_bank.createIndex(
  { "total_experience_years": 1 },
  { name: "idx_total_experience_years", background: true }
);
print("Created: idx_total_experience_years");

db.candidate_bank.createIndex(
  { "experience_years": 1 },
  { name: "idx_experience_years", background: true }
);
print("Created: idx_experience_years");

// Phone normalization for dedup lookups
db.candidate_bank.createIndex(
  { "phone_normalized": 1 },
  { name: "idx_phone_normalized", sparse: true, background: true }
);
print("Created: idx_phone_normalized");

// Bulk import dedup
db.candidate_bank.createIndex(
  { "original_filename": 1, "bulk_import_batch_id": 1 },
  { name: "idx_bulk_import_dedup", background: true }
);
print("Created: idx_bulk_import_dedup");

// Compound for AI search (most common query pattern)
db.candidate_bank.createIndex(
  { "key_skills": 1, "total_experience_years": 1, "location": 1 },
  { name: "idx_search_compound", background: true }
);
print("Created: idx_search_compound");

// Background job polling
db.background_jobs.createIndex(
  { "status": 1, "created_at": -1 },
  { name: "idx_jobs_status_date", background: true }
);
print("Created: idx_jobs_status_date");

db.background_jobs.createIndex(
  { "created_by": 1, "type": 1, "created_at": -1 },
  { name: "idx_jobs_user_type", background: true }
);
print("Created: idx_jobs_user_type");

// Applications scoring
db.applications.createIndex(
  { "score": -1, "created_at": -1 },
  { name: "idx_applications_score", background: true }
);
print("Created: idx_applications_score");

// ============================================================
// STEP 3: UNIQUE EMAIL INDEX (only after confirming no dups)
// ============================================================
if (dupEmails.length === 0) {
  db.candidate_bank.createIndex(
    { "email": 1 },
    { name: "idx_email_unique", unique: true, sparse: true, background: true }
  );
  print("Created: idx_email_unique (unique)");
} else {
  print("\nSKIPPED: idx_email_unique — resolve duplicate emails first.");
  print("Dedup resolution query (keeps most recently updated document):");
  print(`
db.candidate_bank.aggregate([
  { $match: { email: { $exists: true, $ne: null } } },
  { $sort:  { updated_at: -1 } },
  { $group: { _id: "$email", keep: { $first: "$_id" }, all: { $push: "$_id" } } },
  { $project: { to_delete: { $slice: ["$all", 1, 100] } } }
]).forEach(g => {
  if (g.to_delete.length > 0) {
    db.candidate_bank.deleteMany({ _id: { $in: g.to_delete } });
  }
});
  `);
}

print("\n=== Index migration complete ===");
