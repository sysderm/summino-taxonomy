# Deploy Playbook — New 5-Level Taxonomy on scistreak.com

**Generated:** 2026-06-11
**Target:** `sysderm/summino` → scistreak.com (hetz docker)
**Source:** `sysderm/summino-taxonomy@feat/user-facing-taxonomy` commit `73ace76`
**Built file:** `built-taxonomy.json` (2,599 nodes — 20/303/775/1036/465)

## Why this needs a proper PR, not hot-swap

`summino-app/lib/taxonomy.json` is compiled INTO the Next.js bundle (`server.js`) at image build time. There is no mount point for live editing. The deploy must be a real GitHub-CI image rebuild.

## Steps for the deploy PR on `sysderm/summino`

### 1. Drop in new taxonomy.json
```
cp summino-taxonomy/built-taxonomy.json \
   summino/summino-app/lib/taxonomy.json
```

### 2. Update lib/taxonomy.ts types

Current types support 4 levels (Discipline → Specialty → Subspecialty). The new tree has 5. Add a `L5Leaf` (or extend `Specialty` recursively).

```ts
export type Specialty = {
  id: string;
  name: string;
  icon?: string;
  iconifyIcon?: string;
  subspecialties?: Specialty[];  // recursive — handles L4 + L5
  crossListedUnder?: string[];
};
```

Make the type fully recursive (already is — `subspecialties?: Specialty[]`) — the existing code likely just stops descending at L3. Audit `lib/taxonomyUtils.ts` for hard depth assumptions.

### 3. Migration for existing users

`prisma/schema.prisma` Player model has `specialties String[]`. Existing values use OLD taxonomy slugs (`cardiology`, `dermatology`, `computer-science` — most still match in the new tree). Audit:

```bash
docker exec summino-deploy-db-1 psql -U summino_user -d summino \
  -c "SELECT DISTINCT unnest(specialties) FROM \"Player\" ORDER BY 1;"
```

Then `node scripts/migrate-taxonomy-slugs.ts` with a slug map for any that diverged.

### 4. Picker UI verification

The onboarding picker (`summino-app/app/onboarding/page.tsx`) and field selector (`summino-app/components/FieldPicker.tsx`) need to:
- Show L1 grid (20 cards)
- After L1 pick → show L2 grid (max 50 cards for medicine)
- After L2 → show L3 grid
- L4/L5 hidden from picker (used by classifier + search only)

### 5. Classifier prompt update

`summino-ingest/summino_ingest/llm_classifier.py` currently embeds the OLD taxonomy. Bump to:
- Send L1+L2+L3 as the classification target (max ~775 leaf options)
- Optionally send L4 for high-volume L3 like Medicine, CS&AI

### 6. CI + deploy

```bash
# from summino repo
git checkout -b feat/new-taxonomy-2026-06
cp ../summino-taxonomy/built-taxonomy.json summino-app/lib/taxonomy.json
# audit + edit types
# add migration if needed
git commit -am "feat: 5-level user-facing taxonomy (2,599 nodes)"
git push origin feat/new-taxonomy-2026-06
gh pr create ...
# CI builds image; deploy.yml on merge updates IMAGE_TAG on hetz
```

## Trial user creation

Once deployed, create via Prisma seed:
```bash
docker exec summino-deploy-summino-app-1 \
  node -e "import('./server.js').then(...)"
```

Or simpler — bypass the magic-link by inserting directly:
```sql
INSERT INTO "Player" (id, "email", "plan", "specialties", "createdAt")
VALUES (
  gen_random_uuid()::text,
  'taxonomy-test@navarinilab.cloud',
  'pro',
  ARRAY['medicine', 'computer-science-ai'],
  NOW()
);
```

Then visit `https://scistreak.com/signin?email=taxonomy-test@navarinilab.cloud` to receive the magic link.

## ETA estimates

- PR draft + types audit: ~1 hr operator time
- Migration script + test: ~30 min
- CI build: ~10 min
- Deploy + verify: ~10 min
- **Total: ~2 hrs of operator time, all on summino repo, not summino-taxonomy.**
