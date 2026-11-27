<script lang="ts">
  import ParaMap from '$lib/ParaMap.svelte';
  import {
    getOptionsForLayer,
    evaluateGuild,
    rankSpeciesForSite,
    type LayerId,
    type SiteInput,
    type ScoredSpecies,
  } from '$lib/recommender';
  import { lookupLocation, PARA_PRESETS } from '$lib/geo';

  const LAYERS: { id: LayerId; label: string }[] = [
    { id: 'emergent', label: 'Emergent Layer' },
    { id: 'canopy', label: 'Canopy Layer' },
    { id: 'mid', label: 'Mid-Layer' },
    { id: 'lower_mid', label: 'Lower Mid-Layer' },
    { id: 'ground', label: 'Ground Layer (PANCs)' },
  ];

  const GUILD_PRESETS: Record<'5' | '4' | '3', { label: string; layers: LayerId[] }> = {
    '5': { label: '5-Layer Guild', layers: ['emergent', 'canopy', 'mid', 'lower_mid', 'ground'] },
    '4': { label: '4-Layer Guild', layers: ['canopy', 'mid', 'lower_mid', 'ground'] },
    '3': { label: '3-Layer Guild', layers: ['mid', 'lower_mid', 'ground'] },
  };

  // Svelte 5 reactive state
  let step = $state<1 | 2 | 3>(1);
  let locationName = $state(PARA_PRESETS[0].name);
  let geoStatus = $state('');
  let climate = $state(lookupLocation(PARA_PRESETS[0].lat, PARA_PRESETS[0].lon));

  let preferPancs = $state(true);
  let selectedPlantId = $state<string | null>(null);
  let customSlots = $state<Record<LayerId, ScoredSpecies | null> | null>(null);
  let guildMode = $state<'5' | '4' | '3' | 'custom' | null>(null);
  let activeLayers = $state<LayerId[]>([]);

  // Derived site input
  let site = $derived<SiteInput>({
    tempC: climate.tempC,
    rainMm: climate.rainMm,
    soilPh: climate.soilPh,
    drainage: climate.drainage,
    preferPancs,
    primaryCashCropId: selectedPlantId ?? undefined,
  });

  // Compatible plants for Step 2 (no companion bonus yet)
  let compatiblePlants = $derived(rankSpeciesForSite({ ...site, primaryCashCropId: undefined }));
  let inspectedPlant = $derived(
    compatiblePlants.find((p) => p.species.id === selectedPlantId) ?? compatiblePlants[0] ?? null
  );

  // Main plant for Step 3
  let mainPlant = $derived(
    rankSpeciesForSite(site).find((p) => p.species.id === (selectedPlantId ?? inspectedPlant?.species.id)) ?? null
  );

  function emptySlotsWithMain(): Record<LayerId, ScoredSpecies | null> {
    const slots: Record<LayerId, ScoredSpecies | null> = {
      emergent: null,
      canopy: null,
      mid: null,
      lower_mid: null,
      ground: null,
    };
    if (mainPlant) slots[mainPlant.species.layer_id] = mainPlant;
    return slots;
  }

  let guild = $derived(evaluateGuild(customSlots ?? emptySlotsWithMain()));

  // Main plant's layer always first
  let visibleLayers = $derived.by(() => {
    const mainLayerId = mainPlant?.species.layer_id;
    const list = LAYERS.filter((l) => activeLayers.includes(l.id) || l.id === mainLayerId);
    return mainLayerId
      ? [...list.filter((l) => l.id === mainLayerId), ...list.filter((l) => l.id !== mainLayerId)]
      : list;
  });

  let hiddenLayers = $derived(
    LAYERS.filter((l) => !activeLayers.includes(l.id) && l.id !== mainPlant?.species.layer_id)
  );

  function useMyGps() {
    if (!navigator.geolocation) {
      geoStatus = 'GPS not supported in this browser.';
      return;
    }
    geoStatus = 'Getting GPS coordinates...';
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        locationName = `My GPS (${latitude.toFixed(2)}, ${longitude.toFixed(2)})`;
        climate = lookupLocation(latitude, longitude);
        customSlots = null;
        geoStatus = 'Location loaded offline from nearest grid point.';
      },
      () => {
        geoStatus = 'Could not access GPS — click any spot on the map instead.';
      }
    );
  }

  function pickPlant(id: string) {
    selectedPlantId = id;
    customSlots = null;
    guildMode = null;
  }

  function chooseGuildMode(mode: '5' | '4' | '3' | 'custom') {
    guildMode = mode;
    customSlots = emptySlotsWithMain();
    if (mode === 'custom') {
      activeLayers = mainPlant ? [mainPlant.species.layer_id] : [];
    } else {
      activeLayers = [...GUILD_PRESETS[mode].layers];
    }
  }

  function swapSlot(layer: LayerId, speciesId: string) {
    const options = getOptionsForLayer(layer, site);
    const chosen = speciesId ? (options.find((o) => o.species.id === speciesId) ?? null) : null;
    customSlots = { ...guild.slots, [layer]: chosen };
  }

  function addLayer(layer: LayerId) {
    if (!activeLayers.includes(layer)) {
      activeLayers = [...activeLayers, layer];
    }
  }

  function removeLayer(layer: LayerId) {
    activeLayers = activeLayers.filter((id) => id !== layer);
    customSlots = { ...guild.slots, [layer]: null };
  }
</script>

<main style="max-width: 820px; margin: 1.5rem auto; padding: 1rem; font-family: system-ui, sans-serif;">
  <h1 style="margin-bottom: 0.25rem;">Syntropic Guild Builder </h1>

  <!-- Stepper -->
  <div style="display: flex; gap: 0.5rem; margin: 1rem 0 1.5rem;">
    <button onclick={() => (step = 1)} style="flex: 1; padding: 0.6rem; cursor: pointer; font-weight: {step === 1 ? 'bold' : 'normal'}; background: {step === 1 ? '#1b5e20' : '#eee'}; color: {step === 1 ? '#fff' : '#222'}; border: none; border-radius: 6px;">
      1. Location
    </button>
    <button onclick={() => (step = 2)} style="flex: 1; padding: 0.6rem; cursor: pointer; font-weight: {step === 2 ? 'bold' : 'normal'}; background: {step === 2 ? '#1b5e20' : '#eee'}; color: {step === 2 ? '#fff' : '#222'}; border: none; border-radius: 6px;">
      2. Main Plant ({compatiblePlants.length})
    </button>
    <button onclick={() => (step = 3)} style="flex: 1; padding: 0.6rem; cursor: pointer; font-weight: {step === 3 ? 'bold' : 'normal'}; background: {step === 3 ? '#1b5e20' : '#eee'}; color: {step === 3 ? '#fff' : '#222'}; border: none; border-radius: 6px;">
      3. 5-Layer Guild
    </button>
  </div>

  <!-- STEP 1: LOCATION & PARÁ MAP -->
  {#if step === 1}
    <section>
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.75rem;">
        <h2 style="margin: 0;">Pick Location in Pará</h2>
        <button onclick={useMyGps} style="padding: 0.5rem 0.9rem; background: #0d47a1; color: #fff; border: none; border-radius: 6px; cursor: pointer;">
          📍 Use My GPS Location
        </button>
      </div>
      {#if geoStatus}<p style="margin: 0 0 0.75rem; color: #555; font-size: 0.9rem;">{geoStatus}</p>{/if}

      <div style="display: grid; grid-template-columns: 1.2fr 1fr; gap: 1rem; align-items: start;">
        <!-- Interactive Leaflet Satellite/Street Map -->
        <ParaMap
          lat={climate.lat}
          lon={climate.lon}
          onSelect={(newLat, newLon, label) => {
            locationName = label ?? `Custom Point (${newLat.toFixed(2)}, ${newLon.toFixed(2)})`;
            climate = lookupLocation(newLat, newLon);
            customSlots = null;
            geoStatus = '';
          }}
        />

        <!-- Auto-loaded Climate & Soil Card -->
        <div style="border: 1px solid #ddd; border-radius: 8px; padding: 1rem; background: #fafafa;">
          <h3 style="margin-top: 0;">{locationName}</h3>
          <p style="font-size: 0.85rem; color: #666; margin-top: -0.5rem;">
            Lat {climate.lat}, Lon {climate.lon} • Elev {climate.elevationM} m
          </p>

          <div style="display: grid; gap: 0.6rem; margin-top: 1rem;">
            <label>Temp (°C): <input type="number" step="0.1" bind:value={climate.tempC} oninput={() => (customSlots = null)} /></label>
            <label>Annual Rain (mm): <input type="number" bind:value={climate.rainMm} oninput={() => (customSlots = null)} /></label>
            <label>Soil pH: <input type="number" step="0.1" bind:value={climate.soilPh} oninput={() => (customSlots = null)} /></label>
            <label>
              Drainage:
              <select bind:value={climate.drainage} onchange={() => (customSlots = null)}>
                <option value="well_drained">Well Drained (Terra Firme)</option>
                <option value="wet">Wet / Floodplain (Várzea)</option>
              </select>
            </label>
            <label>
              <input type="checkbox" bind:checked={preferPancs} onchange={() => (customSlots = null)} />
              Prioritize PANCs
            </label>
          </div>

          <button
            onclick={() => (step = 2)}
            style="margin-top: 1.25rem; width: 100%; padding: 0.7rem; background: #1b5e20; color: #fff; border: none; border-radius: 6px; font-weight: bold; cursor: pointer;"
          >
            Next: Choose Main Plant ({compatiblePlants.length} fit here) →
          </button>
        </div>
      </div>
    </section>

  <!-- STEP 2: CHOOSE MAIN PLANT & INSPECT INFO -->
  {:else if step === 2}
    <section>
      <h2>Choose Your Main Plant</h2>
      <p style="color: #555; margin-top: -0.5rem;">
        Showing <strong>{compatiblePlants.length}</strong> species suitable for {locationName} ({climate.tempC}°C, {climate.rainMm} mm/yr, pH {climate.soilPh}).
      </p>

      <div style="display: grid; grid-template-columns: 1fr 1.2fr; gap: 1rem; align-items: start;">
        <!-- Clickable Plant List -->
        <div style="display: flex; flex-direction: column; gap: 0.4rem; max-height: 460px; overflow-y: auto; padding-right: 0.25rem;">
          {#each compatiblePlants as item}
            {@const active = inspectedPlant?.species.id === item.species.id}
            <button
              onclick={() => pickPlant(item.species.id)}
              style="text-align: left; padding: 0.65rem; border-radius: 6px; cursor: pointer; border: 2px solid {active ? '#1b5e20' : '#ddd'}; background: {active ? '#e8f5e9' : '#fff'};"
            >
              <div style="display: flex; justify-content: space-between;">
                <strong>{item.species.common_name_pt}</strong>
                <span style="font-size: 0.8rem; color: #2e7d32;">Score {item.score}</span>
              </div>
              <div style="font-size: 0.8rem; color: #555;">
                {item.species.layer_id} • {item.species.role_in_system ?? '—'}
                {#if item.species.is_panc === 1} • 🌿 PANC{/if}
              </div>
            </button>
          {/each}
        </div>

        
        <!-- Selected Plant Info Card -->
        {#if inspectedPlant}
          {@const sp = inspectedPlant.species}
          <div style="border: 1px solid #ccc; border-radius: 8px; padding: 1.1rem; background: #fafafa;">
            <h3 style="margin: 0;">{sp.common_name_pt}</h3>
            <p style="margin: 0.2rem 0 0.8rem; font-style: italic; color: #555;">{sp.scientific_name ?? '—'}</p>

            <div style="display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1rem; font-size: 0.8rem;">
              <span style="background: #e0f2f1; padding: 0.2rem 0.5rem; border-radius: 4px;">Layer: {sp.layer_id}</span>
              {#if sp.succession_stage}<span style="background: #ede7f6; padding: 0.2rem 0.5rem; border-radius: 4px;">{sp.succession_stage}</span>{/if}
              {#if sp.role_in_system}<span style="background: #fff3e0; padding: 0.2rem 0.5rem; border-radius: 4px;">{sp.role_in_system}</span>{/if}
              {#if sp.is_panc === 1}<span style="background: #e8f5e9; padding: 0.2rem 0.5rem; border-radius: 4px;">🌿 PANC</span>{/if}
            </div>

            <div style="font-size: 0.9rem; display: grid; gap: 0.5rem;">
              <div><strong>Harvest:</strong> {sp.harvest_notes_en ?? sp.harvest_notes_pt ?? '—'}</div>
              <div><strong>Layout / Spacing:</strong> {sp.layout_notes ?? '—'}</div>
              <div><strong>Shade Tolerance:</strong> {sp.shade_tolerance ?? '—'}</div>
              <div><strong>Optimal pH:</strong> {sp.soil_ph_min ?? '?'} – {sp.soil_ph_max ?? '?'}</div>
              <div><strong>Optimal Rain:</strong> {sp.opt_rain_min ?? '?'} – {sp.opt_rain_max ?? '?'} mm/yr</div>
              <!-- Red Penalty Breakdown -->
            {#if inspectedPlant.penalties?.length > 0}
              <div style="background: #ffebee; border: 1px solid #ef9a9a; border-left: 4px solid #c62828; color: #b71c1c; padding: 0.6rem 0.75rem; border-radius: 6px; margin-bottom: 0.85rem; font-size: 0.85rem;">
                <strong style="display: block; margin-bottom: 0.2rem;">Why points were deducted here:</strong>
                <ul style="margin: 0; padding-left: 1.2rem;">
                  {#each inspectedPlant.penalties as pen}
                    <li>{pen}</li>
                  {/each}
                </ul>
              </div>
            {/if}

            <!-- Green Bonus Breakdown -->
            {#if inspectedPlant.reasons?.length > 0}
              <div style="background: #e8f5e9; border: 1px solid #a5d6a7; color: #1b5e20; padding: 0.5rem 0.75rem; border-radius: 6px; margin-bottom: 0.85rem; font-size: 0.83rem;">
                <strong>Site bonuses:</strong> {inspectedPlant.reasons.join(' • ')}
              </div>
            {/if}
            </div>

            <button
              onclick={() => {
                selectedPlantId = sp.id;
                customSlots = null;
                guildMode = null;
                step = 3;
              }}
              style="margin-top: 1.25rem; width: 100%; padding: 0.75rem; background: #1b5e20; color: #fff; border: none; border-radius: 6px; font-weight: bold; cursor: pointer;"
            >
              Build Guild Around {sp.common_name_pt} →
            </button>
          </div>
        {/if}
      </div>
    </section>

  <!-- STEP 3: BUILD GUILD & BLUEPRINT -->
  {:else}
    <section>
      <h2 style="margin-top: 0;">Build Your Guild</h2>

      <!-- 1. Choose Guild Type First -->
      <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1.25rem;">
        {#each (['3', '4', '5'] as const) as mode}
          <button
            onclick={() => chooseGuildMode(mode)}
            style="padding: 0.5rem 0.9rem; border-radius: 6px; cursor: pointer; border: 1px solid #1b5e20; background: {guildMode === mode ? '#1b5e20' : '#fff'}; color: {guildMode === mode ? '#fff' : '#1b5e20'};"
          >
            {GUILD_PRESETS[mode].label}
          </button>
        {/each}
        <button
          onclick={() => chooseGuildMode('custom')}
          style="padding: 0.5rem 0.9rem; border-radius: 6px; cursor: pointer; border: 1px solid #1b5e20; background: {guildMode === 'custom' ? '#1b5e20' : '#fff'}; color: {guildMode === 'custom' ? '#fff' : '#1b5e20'};"
        >
          Custom Guild
        </button>
      </div>

      {#if !guildMode}
        <p style="color: #555;">
          Pick a 3, 4, or 5-layer guild above, or start a Custom Guild around
          <strong>{mainPlant?.species.common_name_pt ?? 'your main plant'}</strong>.
        </p>
      {:else}
        {#if guild.warnings.length > 0}
          <div style="background: #fff3cd; border: 1px solid #ffeeba; padding: 0.75rem; border-radius: 6px; margin-bottom: 1rem;">
            {#each guild.warnings as w}
              <p style="margin: 0.25rem 0;">⚠️ {w}</p>
            {/each}
          </div>
        {/if}

        <!-- Layer Cards (Main Plant is always first) -->
        <div style="display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 1rem;">
          {#each visibleLayers as layer}
            {@const options = getOptionsForLayer(layer.id, site)}
            {@const selected = guild.slots[layer.id]}
            {@const isMain = layer.id === mainPlant?.species.layer_id}

            <div style="border: {isMain ? '2px solid #1b5e20' : '1px solid #ddd'}; background: {isMain ? '#f1f8e9' : '#fff'}; padding: 0.75rem; border-radius: 6px;">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <strong>{layer.label}</strong>
                {#if isMain}
                  <span style="font-size: 0.75rem; background: #1b5e20; color: #fff; padding: 0.15rem 0.5rem; border-radius: 4px;">
                    🔒 Main Plant
                  </span>
                {:else if guildMode === 'custom'}
                  <button
                    onclick={() => removeLayer(layer.id)}
                    style="background: none; border: none; color: #c62828; cursor: pointer; font-size: 0.85rem;"
                  >
                    ✕ Remove
                  </button>
                {/if}
              </div>

              {#if isMain && selected}
                <div style="margin-top: 0.4rem; padding: 0.45rem; background: #fff; border: 1px solid #c8e6c9; border-radius: 4px; font-weight: 600;">
                  {selected.species.common_name_pt} ({selected.species.role_in_system ?? '—'}) — Score: {selected.score}
                </div>
              {:else}
                <select
                  style="display: block; width: 100%; margin-top: 0.4rem; padding: 0.45rem;"
                  value={selected?.species.id ?? ''}
                  onchange={(e) => swapSlot(layer.id, e.currentTarget.value)}
                >
                  <option value="">— Choose a plant —</option>
                  {#each options as opt}
                    <option value={opt.species.id}>
                      {opt.species.common_name_pt} ({opt.species.role_in_system ?? '—'}) — Score: {opt.score}
                    </option>
                  {/each}
                </select>
              {/if}

              {#if selected}
                <small style="color: #555;">
                  {selected.species.scientific_name} | {selected.species.succession_stage ?? '—'}
                  {#if selected.reasons.length} • {selected.reasons.join(', ')}{/if}
                </small>
              {/if}
            </div>
          {/each}
        </div>

        <!-- Custom Mode Only: Add Layers -->
        {#if guildMode === 'custom' && hiddenLayers.length > 0}
          <div style="display: flex; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 1.5rem;">
            {#each hiddenLayers as layer}
              <button
                onclick={() => addLayer(layer.id)}
                style="padding: 0.35rem 0.7rem; border-radius: 6px; border: 1px dashed #666; background: #fafafa; cursor: pointer; font-size: 0.85rem;"
              >
                + Add {layer.label}
              </button>
            {/each}
          </div>
        {/if}

        <div style="background: #f4f8f4; padding: 1rem; border-radius: 6px;">
          <h3 style="margin-top: 0;">Planting Line Blueprint</h3>
          <ul>
            {#each guild.blueprint as line}
              <li>{line}</li>
            {/each}
          </ul>
        </div>
      {/if}
    </section>
  {/if}
</main>