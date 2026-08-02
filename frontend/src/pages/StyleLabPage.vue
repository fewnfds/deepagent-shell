<script setup lang="ts">
import { LteButton } from '@adminlte/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import PageShell from '@/components/PageShell.vue'
import '@/styles/style-lab.css'

const { t } = useI18n()
const palette = ref(1)
const demoSwitch = ref(true)
const paletteLabel = computed(() => t(`styleLab.palettes.${palette.value}`))

function remix(): void {
  const choices = [1, 2, 3].filter((value) => value !== palette.value)
  palette.value = choices[Math.floor(Math.random() * choices.length)] ?? 1
  demoSwitch.value = Math.random() >= 0.35
}
</script>

<template>
  <PageShell>
    <template #actions>
      <LteButton theme="info" type="button" @click="remix">
        <i class="bi bi-arrow-clockwise me-2" aria-hidden="true" />
        {{ t('styleLab.remix') }} {{ paletteLabel }}
      </LteButton>
    </template>

    <div class="style-lab" :data-palette="palette">
      <section class="lab-intro">
        <div>
          <span class="lab-kicker">UI SANDBOX / A–J</span>
          <h2>{{ t('styleLab.heading') }}</h2>
          <p>{{ t('styleLab.description') }}</p>
        </div>
        <div class="lab-control-sample">
          <span class="lab-control-label">{{ t('styleLab.switchBaseline') }}</span>
          <div class="form-check form-switch">
            <input
              id="style-lab-switch"
              v-model="demoSwitch"
              class="form-check-input"
              role="switch"
              type="checkbox"
            >
            <label class="form-check-label" for="style-lab-switch">
              {{ demoSwitch ? t('common.enabled') : t('common.disabled') }}
            </label>
          </div>
        </div>
      </section>

      <div class="lab-grid">
        <article class="card card-primary lab-sample">
          <header class="card-header">
            <h3 class="card-title">
              <i class="bi bi-gear me-2" aria-hidden="true" />
              A {{ t('styleLab.cards.adminHeader') }}
            </h3>
          </header>
          <div class="card-body">
            <p class="text-body-secondary">{{ t('styleLab.cards.adminHeaderDetail') }}</p>
            <label class="form-label" for="lab-a-input">Base URL</label>
            <input id="lab-a-input" class="form-control" readonly value="http://127.0.0.1:19100/v1">
          </div>
        </article>

        <article class="card card-outline card-info lab-sample">
          <header class="card-header">
            <h3 class="card-title">
              <i class="bi bi-info-circle me-2" aria-hidden="true" />
              B {{ t('styleLab.cards.adminOutline') }}
            </h3>
          </header>
          <div class="card-body">
            <p class="text-body-secondary">{{ t('styleLab.cards.adminOutlineDetail') }}</p>
            <div class="lab-actions">
              <span class="badge text-bg-info">API</span>
              <span class="badge text-bg-success">READY</span>
            </div>
          </div>
        </article>

        <article class="lab-card lab-card--rail">
          <header class="lab-card__header">
            <span class="lab-card__icon"><i class="bi bi-sliders" aria-hidden="true" /></span>
            <div>
              <span class="lab-card__eyebrow">CONTROL</span>
              <h3>C {{ t('styleLab.cards.rail') }}</h3>
            </div>
          </header>
          <div class="lab-card__body">
            <p>{{ t('styleLab.cards.railDetail') }}</p>
            <div class="lab-mini-field">
              <span>{{ t('eventFeed.controls.verbose') }}</span>
              <strong>ON</strong>
            </div>
          </div>
        </article>

        <article class="lab-card lab-card--aurora">
          <header class="lab-card__header">
            <span class="lab-card__eyebrow">AURORA PANEL</span>
            <span class="badge text-bg-primary">LIVE</span>
          </header>
          <div class="lab-card__body">
            <h3>D {{ t('styleLab.cards.aurora') }}</h3>
            <p>{{ t('styleLab.cards.auroraDetail') }}</p>
            <div class="lab-kpi-row">
              <strong>24</strong>
              <span>events / min</span>
            </div>
          </div>
        </article>

        <article class="lab-card lab-card--terminal">
          <header class="lab-card__header">
            <div class="lab-terminal-dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <span>runtime://diagnostics</span>
          </header>
          <div class="lab-card__body">
            <h3>E {{ t('styleLab.cards.terminal') }}</h3>
            <p class="lab-terminal-line"><span>$</span> agent-shell status --verbose</p>
            <p class="lab-terminal-line"><span>✓</span> API Server ready</p>
          </div>
        </article>

        <article class="lab-card lab-card--layered">
          <header class="lab-card__header">
            <span class="lab-card__index">F</span>
            <div>
              <span class="lab-card__eyebrow">STACKED HEADER</span>
              <h3>{{ t('styleLab.cards.layered') }}</h3>
            </div>
          </header>
          <div class="lab-card__body">
            <p>{{ t('styleLab.cards.layeredDetail') }}</p>
            <div class="lab-actions">
              <button class="btn btn-primary btn-sm" type="button">Save</button>
              <button class="btn btn-warning btn-sm" type="button">Reset</button>
            </div>
          </div>
        </article>

        <article class="lab-card lab-card--glass">
          <header class="lab-card__header">
            <i class="bi bi-circle-half" aria-hidden="true" />
            <span class="lab-card__eyebrow">TRANSLUCENT</span>
          </header>
          <div class="lab-card__body">
            <h3>G {{ t('styleLab.cards.glass') }}</h3>
            <p>{{ t('styleLab.cards.glassDetail') }}</p>
            <div class="lab-swatch-row" aria-hidden="true">
              <span class="lab-swatch" />
              <span class="lab-swatch" />
              <span class="lab-swatch" />
            </div>
          </div>
        </article>

        <article class="lab-card lab-card--dense">
          <header class="lab-card__header">
            <div>
              <span class="lab-card__eyebrow">DENSE DATA</span>
              <h3>H {{ t('styleLab.cards.dense') }}</h3>
            </div>
            <span class="lab-dot" aria-label="online" />
          </header>
          <div class="lab-card__body">
            <dl class="lab-definition-list">
              <div><dt>Host</dt><dd>127.0.0.1</dd></div>
              <div><dt>Port</dt><dd>19100</dd></div>
              <div><dt>Mode</dt><dd>Local</dd></div>
            </dl>
          </div>
        </article>

        <article class="lab-card lab-card--corner">
          <span class="lab-corner-mark"><i class="bi bi-check-lg" aria-hidden="true" /></span>
          <header class="lab-card__header">
            <span class="lab-card__eyebrow">STATUS CARD</span>
            <h3>I {{ t('styleLab.cards.corner') }}</h3>
          </header>
          <div class="lab-card__body">
            <strong class="lab-status-value">Healthy</strong>
            <p>{{ t('styleLab.cards.cornerDetail') }}</p>
          </div>
        </article>

        <article class="lab-card lab-card--split">
          <header class="lab-card__header">
            <span class="lab-card__icon"><i class="bi bi-boxes" aria-hidden="true" /></span>
            <div>
              <span class="lab-card__eyebrow">ACTION PANEL</span>
              <h3>J {{ t('styleLab.cards.split') }}</h3>
            </div>
          </header>
          <div class="lab-card__body">
            <p>{{ t('styleLab.cards.splitDetail') }}</p>
          </div>
          <footer class="lab-card__footer">
            <span>3 changes</span>
            <button class="btn btn-primary btn-sm" type="button">Apply</button>
          </footer>
        </article>
      </div>
    </div>
  </PageShell>
</template>
