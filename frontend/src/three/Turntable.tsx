// El tocadiscos 3D, modelado sobre un plato de tracción directa de club tipo «1200»: chasis
// negro mate, plato con cuatro filas de puntos estroboscópicos, luz estroboscópica roja,
// rueda moleteada, START · STOP, 33/45, brazo en S, fader de pitch y patas moleteadas.
// La marca es SetID (no se reproduce ningún logotipo ajeno).
//
// El disco representa el set: cada track identificado es una banda de surcos iluminada en su
// posición (de fuera hacia dentro) y la aguja avanza con el análisis real.
//
// Coordenadas: 1 unidad = 100 mm; origen en el centro de la cubierta, y = 0 en su superficie.

import {
  ContactShadows,
  Environment,
  Lightformer,
  MeshReflectorMaterial,
  PerformanceMonitor,
  RoundedBox,
} from '@react-three/drei'
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber'
import { Bloom, EffectComposer, Vignette } from '@react-three/postprocessing'
import { easing } from 'maath'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import * as THREE from 'three'

import {
  brushedDiscTexture,
  deckPrintTexture,
  keyLabelTexture,
  knurlTexture,
  slipmatTexture,
  strobeRimTexture,
} from './deckTextures'
import {
  ARM_PIVOT,
  ARM_REST_R,
  GROOVE_OUTER,
  LABEL_R,
  PLATTER_R,
  RECORD_R,
  bandIntensity,
  needleRadius,
  radiusAt,
  targetSpin,
  tonearmYaw,
  type GrooveBand,
  type TurntableMode,
} from './model'
import { grooveRoughnessTexture, labelTexture } from './textures'

const SIGNAL = new THREE.Color('#7dd3fc')
// Edición SetID: pilotos y luz estroboscópica en azul hielo, a juego con la interfaz.
const LED = new THREE.Color('#38bdf8')

// Chasis y posiciones medidas sobre la vista cenital del original.
const DECK_W = 4.53
const DECK_D = 3.53
const PLATTER_AT = new THREE.Vector3(-0.6, 0, -0.11)
const PIVOT_AT = new THREE.Vector3(PLATTER_AT.x + ARM_PIVOT.x, 0, PLATTER_AT.z + ARM_PIVOT.z)
const FADER = { x: 1.84, z0: 0.12, z1: 1.28 }
const RESET_AT = { x: 1.5, z: 1.05 }
const KNOB_AT = { x: -1.91, z: 0.95 }
const LOGO_AT = { x: 0.42, z: 1.46 }

// Alturas del plato (sobre la cubierta).
const RIM_BOTTOM = 0.1
const RIM_TOP = 0.145
const MAT_TOP = 0.157
const RECORD_Y = MAT_TOP + 0.011
const RECORD_TOP = RECORD_Y + 0.011
const ARM_TUBE_Y = RECORD_TOP + 0.158

const MATTE = { color: '#17181b', roughness: 0.62, metalness: 0.12 }

export interface TurntableProps {
  mode: TurntableMode
  duration: number | null
  bands: GrooveBand[]
  scannedS: number | null
  reducedMotion: boolean
  frameloop: 'always' | 'demand' | 'never'
  catalog?: string
  hovered: number | null
  onHover(band: GrooveBand | null, x: number, y: number): void
  onSelect(band: GrooveBand): void
}

/** Crea un recurso de three.js una vez (o al cambiar `key`) y lo libera al desmontar. */
function useDisposable<T extends { dispose(): void }>(factory: () => T, key: unknown = null): T {
  const value = useMemo(() => factory(), [key]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => value.dispose(), [value])
  return value
}

// --- Chasis ----------------------------------------------------------------------------

function Foot({ x, z, knurl }: { x: number; z: number; knurl: THREE.Texture }) {
  return (
    <group position={[x, -0.86, z]}>
      {/* Cuña esculpida del chasis sobre la pata */}
      <mesh position={[0, -0.06, 0]} castShadow>
        <cylinderGeometry args={[0.33, 0.42, 0.12, 64]} />
        <meshStandardMaterial {...MATTE} />
      </mesh>
      {/* Pata moleteada (aislante de altura regulable) */}
      <mesh position={[0, -0.25, 0]} castShadow>
        <cylinderGeometry args={[0.34, 0.34, 0.26, 96, 1]} />
        <meshStandardMaterial
          color="#141517"
          roughness={0.5}
          metalness={0.3}
          bumpMap={knurl}
          bumpScale={1.4}
        />
      </mesh>
    </group>
  )
}

function Plinth() {
  const knurl = useDisposable(() => {
    const t = knurlTexture()
    t.repeat.set(4, 1)
    return t
  })
  const print = useDisposable(() =>
    deckPrintTexture({
      width: DECK_W,
      depth: DECK_D,
      scale: 420,
      fader: FADER,
      reset: RESET_AT,
      knob: KNOB_AT,
      logo: LOGO_AT,
      model: 'SID-1200',
    }),
  )
  const fx = DECK_W / 2 - 0.42
  const fz = DECK_D / 2 - 0.38
  return (
    <group>
      {/* Cubierta superior */}
      <RoundedBox
        args={[DECK_W, 0.12, DECK_D]}
        radius={0.025}
        smoothness={4}
        position={[0, -0.06, 0]}
        castShadow
        receiveShadow
      >
        <meshStandardMaterial {...MATTE} />
      </RoundedBox>
      {/* Junta entre cubierta y cuerpo */}
      <mesh position={[0, -0.128, 0]}>
        <boxGeometry args={[DECK_W - 0.04, 0.016, DECK_D - 0.04]} />
        <meshStandardMaterial color="#08080a" roughness={0.9} />
      </mesh>
      {/* Cuerpo */}
      <RoundedBox
        args={[DECK_W - 0.01, 0.72, DECK_D - 0.01]}
        radius={0.07}
        smoothness={5}
        position={[0, -0.496, 0]}
        castShadow
        receiveShadow
      >
        <meshStandardMaterial color="#131416" roughness={0.55} metalness={0.15} />
      </RoundedBox>
      <Foot x={-fx} z={-fz} knurl={knurl} />
      <Foot x={fx} z={-fz} knurl={knurl} />
      <Foot x={-fx} z={fz} knurl={knurl} />
      <Foot x={fx} z={fz} knurl={knurl} />
      {/* Serigrafía */}
      <mesh position={[0, 0.0012, 0]} rotation-x={-Math.PI / 2}>
        <planeGeometry args={[DECK_W, DECK_D]} />
        <meshStandardMaterial
          map={print}
          transparent
          depthWrite={false}
          roughness={0.5}
          polygonOffset
          polygonOffsetFactor={-2}
        />
      </mesh>
      {/* Rebaje de la base del brazo */}
      <mesh position={[PIVOT_AT.x, 0.0015, PIVOT_AT.z]} rotation-x={-Math.PI / 2}>
        <circleGeometry args={[0.6, 96]} />
        <meshStandardMaterial color="#0c0c0e" roughness={0.7} />
      </mesh>
      <mesh position={[PIVOT_AT.x, 0.002, PIVOT_AT.z]} rotation-x={-Math.PI / 2}>
        <ringGeometry args={[0.6, 0.615, 96]} />
        <meshStandardMaterial color="#2a2c31" metalness={0.6} roughness={0.35} />
      </mesh>
    </group>
  )
}

// --- Controles -------------------------------------------------------------------------

function Key({
  at,
  size,
  label,
  led,
  ledOn = false,
  labelOptions,
}: {
  at: [number, number]
  size: [number, number, number]
  label: string
  led?: [number, number]
  ledOn?: boolean
  labelOptions?: Parameters<typeof keyLabelTexture>[1]
}) {
  const texture = useDisposable(() => keyLabelTexture(label, labelOptions), label)
  const [w, h, d] = size
  return (
    <group position={[at[0], h / 2, at[1]]}>
      <RoundedBox args={size} radius={0.012} smoothness={3} castShadow>
        <meshStandardMaterial color="#1d1e22" roughness={0.5} metalness={0.2} />
      </RoundedBox>
      <mesh position={[0, h / 2 + 0.0008, 0]} rotation-x={-Math.PI / 2}>
        <planeGeometry args={[w - 0.025, d - 0.025]} />
        <meshStandardMaterial map={texture} roughness={0.55} />
      </mesh>
      {led && (
        <mesh position={[led[0], h / 2 + 0.002, led[1]]} rotation-x={-Math.PI / 2}>
          <planeGeometry args={[0.07, 0.016]} />
          <meshBasicMaterial
            color={ledOn ? LED.clone().multiplyScalar(2.2) : '#2b2c30'}
            toneMapped={!ledOn}
          />
        </mesh>
      )}
    </group>
  )
}

function Controls({ mode }: { mode: TurntableMode }) {
  const knurl = useDisposable(() => {
    const t = knurlTexture(1024, 64, 140)
    t.repeat.set(2, 1)
    return t
  })
  const brushed = useDisposable(() => brushedDiscTexture(512, 92))
  const darkBrushed = useDisposable(() => brushedDiscTexture(256, 40))
  const running = mode !== 'idle'
  return (
    <group>
      {/* Rueda de encendido con anillo LED */}
      <group position={[KNOB_AT.x, 0, KNOB_AT.z]}>
        <mesh position={[0, 0.08, 0]} castShadow>
          <cylinderGeometry args={[0.15, 0.155, 0.16, 96, 1, true]} />
          <meshStandardMaterial
            color="#202125"
            metalness={0.6}
            roughness={0.38}
            bumpMap={knurl}
            bumpScale={1.2}
          />
        </mesh>
        <mesh position={[0, 0.161, 0]} rotation-x={-Math.PI / 2}>
          <circleGeometry args={[0.15, 96]} />
          <meshStandardMaterial map={brushed} metalness={0.85} roughness={0.28} />
        </mesh>
        <mesh position={[0, 0.006, 0]} rotation-x={-Math.PI / 2} rotation-z={-Math.PI * 0.1}>
          <ringGeometry args={[0.172, 0.19, 64, 1, 0, Math.PI * 0.9]} />
          <meshBasicMaterial
            color={LED.clone().multiplyScalar(running ? 2.5 : 0.6)}
            toneMapped={false}
          />
        </mesh>
      </group>

      <Key
        at={[-1.84, 1.45]}
        size={[0.46, 0.045, 0.36]}
        label="START · STOP"
        labelOptions={{ w: 512, h: 400, size: 0.075 }}
      />
      <Key
        at={[-1.38, 1.57]}
        size={[0.3, 0.035, 0.09]}
        label="33"
        led={[0.06, 0]}
        ledOn
        labelOptions={{ w: 512, h: 160, size: 0.24, align: 'left' }}
      />
      <Key
        at={[-1.03, 1.57]}
        size={[0.3, 0.035, 0.09]}
        label="45"
        led={[0.06, 0]}
        labelOptions={{ w: 512, h: 160, size: 0.24, align: 'left' }}
      />

      {/* Portaadaptador de 45 rpm */}
      <group position={[-1.84, 0, -1.48]}>
        <mesh position={[0, 0.002, 0]} rotation-x={-Math.PI / 2}>
          <circleGeometry args={[0.22, 64]} />
          <meshStandardMaterial color="#0b0b0d" roughness={0.8} />
        </mesh>
        <mesh position={[0, 0.02, 0]} castShadow>
          <cylinderGeometry args={[0.19, 0.2, 0.035, 64]} />
          <meshStandardMaterial color="#1a1b1e" metalness={0.5} roughness={0.35} />
        </mesh>
        <mesh position={[0, 0.0385, 0]} rotation-x={-Math.PI / 2}>
          <circleGeometry args={[0.022, 24]} />
          <meshStandardMaterial color="#050506" />
        </mesh>
      </group>

      {/* Luz de puntería (target light) */}
      <group position={[0.28, 0, 1.52]}>
        <mesh position={[0, 0.17, 0]} castShadow>
          <cylinderGeometry args={[0.045, 0.05, 0.34, 32]} />
          <meshStandardMaterial {...MATTE} roughness={0.45} />
        </mesh>
        <mesh position={[0, 0.341, 0]} rotation-x={-Math.PI / 2}>
          <circleGeometry args={[0.045, 32]} />
          <meshStandardMaterial map={darkBrushed} metalness={0.7} roughness={0.35} />
        </mesh>
      </group>

      {/* Fader de pitch */}
      <group position={[FADER.x, 0, (FADER.z0 + FADER.z1) / 2]}>
        <RoundedBox
          args={[0.27, 0.022, FADER.z1 - FADER.z0 + 0.26]}
          radius={0.01}
          smoothness={3}
          position={[0, 0.011, 0]}
        >
          <meshStandardMaterial color="#111214" roughness={0.6} metalness={0.2} />
        </RoundedBox>
        <mesh position={[0, 0.0225, 0]} rotation-x={-Math.PI / 2}>
          <planeGeometry args={[0.05, FADER.z1 - FADER.z0]} />
          <meshStandardMaterial color="#030304" roughness={1} />
        </mesh>
        <RoundedBox
          args={[0.22, 0.08, 0.13]}
          radius={0.02}
          smoothness={4}
          position={[0, 0.06, 0]}
          castShadow
        >
          <meshStandardMaterial color="#1c1d21" metalness={0.45} roughness={0.32} />
        </RoundedBox>
        <mesh position={[0, 0.1005, 0]} rotation-x={-Math.PI / 2}>
          <planeGeometry args={[0.2, 0.012]} />
          <meshStandardMaterial color="#d8dbe0" metalness={1} roughness={0.2} />
        </mesh>
      </group>
      {/* Piloto del 0 % */}
      <mesh
        position={[FADER.x - 0.23, 0.0025, (FADER.z0 + FADER.z1) / 2]}
        rotation-x={-Math.PI / 2}
      >
        <planeGeometry args={[0.065, 0.02]} />
        <meshBasicMaterial color={LED.clone().multiplyScalar(2)} toneMapped={false} />
      </mesh>
      <Key
        at={[FADER.x, FADER.z0 - 0.3]}
        size={[0.22, 0.03, 0.09]}
        label="×2"
        led={[0.05, 0]}
        ledOn
        labelOptions={{ w: 512, h: 200, size: 0.22, align: 'left' }}
      />

      {/* RESET */}
      <group position={[RESET_AT.x, 0, RESET_AT.z]}>
        <mesh position={[0, 0.016, 0]} castShadow>
          <cylinderGeometry args={[0.085, 0.09, 0.032, 48]} />
          <meshStandardMaterial color="#1b1c1f" metalness={0.5} roughness={0.35} />
        </mesh>
        <mesh position={[0, 0.0325, 0]} rotation-x={-Math.PI / 2}>
          <circleGeometry args={[0.085, 48]} />
          <meshStandardMaterial map={darkBrushed} metalness={0.8} roughness={0.3} />
        </mesh>
      </group>
    </group>
  )
}

// --- Plato y disco ---------------------------------------------------------------------

function Platter({
  mode,
  reducedMotion,
  catalog,
  showRecord,
}: {
  mode: TurntableMode
  reducedMotion: boolean
  catalog?: string
  showRecord: boolean
}) {
  const spinner = useRef<THREE.Group>(null)
  const record = useRef<THREE.Group>(null)
  const speed = useRef(reducedMotion ? 0 : targetSpin(mode))
  const drop = useRef(showRecord ? 0 : 1)
  const rim = useDisposable(() => strobeRimTexture())
  const mat = useDisposable(() => slipmatTexture())
  const grooves = useDisposable(() => grooveRoughnessTexture())
  const label = useDisposable(() => labelTexture(1024, catalog), catalog)

  useFrame((_, dt) => {
    if (spinner.current) {
      const target = reducedMotion ? 0 : targetSpin(mode)
      // Inercia del motor de tracción directa: arranca y frena en algo más de un segundo.
      speed.current = THREE.MathUtils.damp(speed.current, target, 1.8, dt)
      spinner.current.rotation.y -= speed.current * dt
    }
    if (record.current) {
      // El disco «cae» sobre el plato al cargar un set y se retira al quitarlo.
      drop.current = reducedMotion
        ? showRecord
          ? 0
          : 1
        : THREE.MathUtils.damp(drop.current, showRecord ? 0 : 1, 4, dt)
      record.current.position.y = RECORD_Y + drop.current * 0.9
      record.current.visible = drop.current < 0.98
    }
  })

  return (
    <group position={PLATTER_AT}>
      {/* Base fija bajo el plato */}
      <mesh position={[0, 0.01, 0]}>
        <cylinderGeometry args={[PLATTER_R - 0.03, PLATTER_R - 0.03, 0.02, 128]} />
        <meshStandardMaterial color="#060607" roughness={0.9} />
      </mesh>
      {/* Luz estroboscópica: emisor rojo junto al borde delantero izquierdo */}
      <group position={[-1.3, 0, 0.98]}>
        <mesh position={[0, 0.004, 0]} rotation-x={-Math.PI / 2} rotation-z={0.65}>
          <planeGeometry args={[0.14, 0.05]} />
          <meshBasicMaterial color={LED.clone().multiplyScalar(3)} toneMapped={false} />
        </mesh>
        <pointLight
          position={[0, 0.06, 0]}
          color="#38bdf8"
          intensity={2.2}
          distance={0.85}
          decay={2}
        />
      </group>

      <group ref={spinner}>
        {/* Canto del plato */}
        <mesh position={[0, (0.02 + RIM_BOTTOM) / 2, 0]} castShadow receiveShadow>
          <cylinderGeometry args={[PLATTER_R, PLATTER_R, RIM_BOTTOM - 0.02, 192, 1, true]} />
          <meshStandardMaterial
            color="#1a1b1e"
            metalness={0.7}
            roughness={0.35}
            side={THREE.DoubleSide}
          />
        </mesh>
        {/* Bisel con los puntos estroboscópicos */}
        <mesh position={[0, (RIM_BOTTOM + RIM_TOP) / 2, 0]}>
          <cylinderGeometry
            args={[PLATTER_R - 0.09, PLATTER_R, RIM_TOP - RIM_BOTTOM, 256, 1, true]}
          />
          <meshStandardMaterial map={rim} metalness={0.75} roughness={0.3} />
        </mesh>
        {/* Labios cromados */}
        <mesh position={[0, RIM_BOTTOM, 0]} rotation-x={Math.PI / 2}>
          <torusGeometry args={[PLATTER_R, 0.007, 12, 256]} />
          <meshStandardMaterial color="#e6e8ec" metalness={1} roughness={0.12} />
        </mesh>
        <mesh position={[0, RIM_TOP, 0]} rotation-x={Math.PI / 2}>
          <torusGeometry args={[PLATTER_R - 0.09, 0.005, 12, 256]} />
          <meshStandardMaterial color="#e6e8ec" metalness={1} roughness={0.12} />
        </mesh>
        {/* Alfombrilla de fieltro */}
        <mesh position={[0, RIM_TOP + 0.006, 0]} receiveShadow>
          <cylinderGeometry args={[PLATTER_R - 0.1, PLATTER_R - 0.1, 0.012, 192]} />
          <meshStandardMaterial attach="material-0" color="#202124" roughness={1} />
          <meshStandardMaterial attach="material-1" map={mat} roughness={0.95} />
          <meshStandardMaterial attach="material-2" color="#111" />
        </mesh>
        {/* Eje */}
        <mesh position={[0, MAT_TOP + 0.06, 0]}>
          <cylinderGeometry args={[0.018, 0.018, 0.12, 24]} />
          <meshStandardMaterial color="#d9dbe0" metalness={1} roughness={0.15} />
        </mesh>
        <mesh position={[0, MAT_TOP + 0.12, 0]}>
          <sphereGeometry args={[0.018, 16, 12]} />
          <meshStandardMaterial color="#d9dbe0" metalness={1} roughness={0.15} />
        </mesh>

        {/* Vinilo */}
        <group ref={record} position={[0, RECORD_Y, 0]}>
          <mesh castShadow receiveShadow>
            <cylinderGeometry args={[RECORD_R, RECORD_R, 0.022, 160, 1]} />
            <meshPhysicalMaterial
              color="#0b0b0d"
              roughness={0.5}
              roughnessMap={grooves}
              metalness={0.1}
              clearcoat={0.7}
              clearcoatRoughness={0.25}
            />
          </mesh>
          <mesh position={[0, 0.0115, 0]} rotation-x={-Math.PI / 2}>
            <circleGeometry args={[LABEL_R, 96]} />
            <meshBasicMaterial map={label} toneMapped={false} color="#e8e8e8" />
          </mesh>
        </group>
      </group>
    </group>
  )
}

function GrooveRing({
  band,
  active,
  onHover,
  onSelect,
}: {
  band: GrooveBand
  active: boolean
  onHover: TurntableProps['onHover']
  onSelect: TurntableProps['onSelect']
}) {
  const material = useRef<THREE.MeshBasicMaterial>(null)
  const appear = useRef(0)
  const color = useMemo(() => new THREE.Color(), [])

  useFrame((_, dt) => {
    if (!material.current) return
    appear.current = THREE.MathUtils.damp(appear.current, 1, 3, dt)
    // Luz aditiva: los surcos negros se siguen viendo debajo, como si brillaran por dentro.
    const intensity = bandIntensity(band) * (active ? 2 : 1)
    if (band.unknown) color.setRGB(0.5, 0.5, 0.56).multiplyScalar(intensity)
    else color.copy(SIGNAL).multiplyScalar(intensity)
    material.current.color.copy(color)
    material.current.opacity = appear.current * (band.unknown ? 0.6 : 0.85)
  })

  const pointer = (e: ThreeEvent<PointerEvent>, value: GrooveBand | null) => {
    e.stopPropagation()
    onHover(value, e.nativeEvent.clientX, e.nativeEvent.clientY)
  }

  return (
    <mesh
      onPointerOver={(e) => pointer(e, band)}
      onPointerMove={(e) => pointer(e, band)}
      onPointerOut={(e) => pointer(e, null)}
      onClick={(e) => {
        e.stopPropagation()
        onSelect(band)
      }}
    >
      <ringGeometry args={[band.inner, band.outer, 160, 1]} />
      <meshBasicMaterial
        ref={material}
        transparent
        toneMapped={false}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </mesh>
  )
}

function SetGrooves({
  bands,
  hovered,
  onHover,
  onSelect,
  mode,
  scannedS,
  duration,
}: Pick<
  TurntableProps,
  'bands' | 'hovered' | 'onHover' | 'onSelect' | 'mode' | 'scannedS' | 'duration'
>) {
  const playedInner = mode === 'playing' && duration ? radiusAt(scannedS ?? 0, duration) : null
  return (
    <group position={[PLATTER_AT.x, RECORD_TOP + 0.0006, PLATTER_AT.z]} rotation-x={-Math.PI / 2}>
      {playedInner !== null && GROOVE_OUTER - playedInner > 0.003 && (
        <mesh>
          <ringGeometry args={[playedInner, GROOVE_OUTER, 160, 1]} />
          <meshBasicMaterial color="#ffffff" transparent opacity={0.035} depthWrite={false} />
        </mesh>
      )}
      {bands.map((band) => (
        <GrooveRing
          key={`${band.position}-${band.startS}`}
          band={band}
          active={hovered === band.position}
          onHover={onHover}
          onSelect={onSelect}
        />
      ))}
    </group>
  )
}

// --- Brazo en S --------------------------------------------------------------------------

/** Curva del brazo en coordenadas locales: +X va del pivote a la aguja. */
function armCurve(): THREE.CatmullRomCurve3 {
  return new THREE.CatmullRomCurve3([
    new THREE.Vector3(0.02, 0, 0),
    new THREE.Vector3(0.5, 0, 0.07),
    new THREE.Vector3(1.05, 0, 0.115),
    new THREE.Vector3(1.55, 0, 0.075),
    new THREE.Vector3(1.88, 0, -0.03),
    new THREE.Vector3(2.02, 0, -0.075),
  ])
}

function Tonearm({
  mode,
  scannedS,
  duration,
  reducedMotion,
}: Pick<TurntableProps, 'mode' | 'scannedS' | 'duration' | 'reducedMotion'>) {
  const yawGroup = useRef<THREE.Group>(null)
  const liftGroup = useRef<THREE.Group>(null)
  const initialYaw = useMemo(() => tonearmYaw(needleRadius(mode, scannedS, duration)), []) // eslint-disable-line react-hooks/exhaustive-deps
  const tube = useDisposable(() => new THREE.TubeGeometry(armCurve(), 96, 0.022, 20, false))
  const knurl = useDisposable(() => {
    const t = knurlTexture(1024, 64, 160)
    t.repeat.set(3, 1)
    return t
  })
  const cap = useDisposable(() => brushedDiscTexture(256, 60))
  const restYaw = useMemo(() => tonearmYaw(ARM_REST_R), [])

  useFrame((_, dt) => {
    if (!yawGroup.current || !liftGroup.current) return
    const yaw = tonearmYaw(needleRadius(mode, scannedS, duration))
    // La aguja solo baja al disco mientras se analiza; si no, el brazo queda levantado.
    const lift = mode === 'playing' ? 0 : mode === 'cue' ? 0.035 : 0.012
    const smooth = reducedMotion ? 0.001 : mode === 'playing' ? 0.6 : 0.4
    easing.damp(yawGroup.current.rotation, 'y', yaw, smooth, dt)
    easing.damp(liftGroup.current.rotation, 'z', lift, 0.3, dt)
  })

  const black = (extra: Partial<THREE.MeshStandardMaterialParameters> = {}): ReactNode => (
    <meshStandardMaterial color="#141518" metalness={0.55} roughness={0.32} {...extra} />
  )
  const chrome = <meshStandardMaterial color="#d9dbe0" metalness={1} roughness={0.15} />

  // Soporte de reposo: bajo el tubo, a dos tercios del brazo cuando está aparcado.
  const restAt = new THREE.Vector3(1.45, 0, 0.11).applyAxisAngle(
    new THREE.Vector3(0, 1, 0),
    restYaw,
  )

  return (
    <group position={PIVOT_AT}>
      {/* Anillo de altura, moleteado */}
      <mesh position={[0, 0.06, 0]} castShadow>
        <cylinderGeometry args={[0.36, 0.38, 0.12, 96, 1]} />
        {black({ bumpMap: knurl, bumpScale: 1, roughness: 0.45 })}
      </mesh>
      <mesh position={[0, 0.121, 0]} rotation-x={-Math.PI / 2}>
        <ringGeometry args={[0.2, 0.36, 96]} />
        {black({ roughness: 0.4 })}
      </mesh>
      {/* Torre del cardán */}
      <mesh position={[0, ARM_TUBE_Y / 2 + 0.06, 0]} castShadow>
        <cylinderGeometry args={[0.13, 0.18, ARM_TUBE_Y - 0.06, 48]} />
        {black()}
      </mesh>
      {/* Dial antiskating */}
      <group position={[0.36, 0, 0.12]}>
        <mesh position={[0, 0.16, 0]} castShadow>
          <cylinderGeometry args={[0.1, 0.1, 0.07, 48]} />
          {black({ bumpMap: knurl, bumpScale: 0.6 })}
        </mesh>
        <mesh position={[0, 0.1955, 0]} rotation-x={-Math.PI / 2}>
          <circleGeometry args={[0.1, 48]} />
          <meshStandardMaterial map={cap} metalness={0.8} roughness={0.3} />
        </mesh>
      </group>
      {/* Palanca de elevación */}
      <group position={[0.2, 0.2, 0.36]} rotation-y={-0.5}>
        <mesh castShadow>
          <cylinderGeometry args={[0.035, 0.035, 0.12, 20]} />
          {black()}
        </mesh>
        <mesh position={[0.09, 0.07, 0]} rotation-z={-0.6} castShadow>
          <boxGeometry args={[0.2, 0.02, 0.04]} />
          {black()}
        </mesh>
      </group>
      {/* Soporte de reposo */}
      <group position={[restAt.x, 0, restAt.z]}>
        <mesh position={[0, ARM_TUBE_Y / 2 - 0.01, 0]} castShadow>
          <cylinderGeometry args={[0.025, 0.03, ARM_TUBE_Y - 0.02, 16]} />
          {black()}
        </mesh>
        <mesh position={[0, ARM_TUBE_Y - 0.03, 0]}>
          <boxGeometry args={[0.07, 0.03, 0.09]} />
          {black({ roughness: 0.6 })}
        </mesh>
      </group>

      <group ref={yawGroup} rotation-y={initialYaw}>
        <group ref={liftGroup} position={[0, ARM_TUBE_Y, 0]}>
          {/* Cardán */}
          <mesh castShadow>
            <boxGeometry args={[0.2, 0.12, 0.16]} />
            {black()}
          </mesh>
          {/* Contrapeso y su eje */}
          <mesh position={[-0.33, 0, 0]} rotation-z={Math.PI / 2}>
            <cylinderGeometry args={[0.03, 0.03, 0.46, 16]} />
            {black()}
          </mesh>
          <mesh position={[-0.47, 0, 0]} rotation-z={Math.PI / 2} castShadow>
            <cylinderGeometry args={[0.15, 0.15, 0.24, 64]} />
            {black({ bumpMap: knurl, bumpScale: 0.5 })}
          </mesh>
          <mesh position={[-0.59, 0, 0]} rotation-y={-Math.PI / 2}>
            <circleGeometry args={[0.15, 64]} />
            <meshStandardMaterial map={cap} metalness={0.85} roughness={0.28} />
          </mesh>
          {/* Tubo en S */}
          <mesh geometry={tube} castShadow>
            {black({ roughness: 0.28 })}
          </mesh>
          {/* Collar del portacápsulas */}
          <mesh position={[2.02, 0, -0.075]} rotation-z={Math.PI / 2}>
            <cylinderGeometry args={[0.03, 0.03, 0.06, 20]} />
            {chrome}
          </mesh>
          {/* Portacápsulas, con el ángulo de offset del original */}
          <group position={[2.17, -0.09, -0.06]} rotation-y={0.38}>
            <mesh castShadow>
              <boxGeometry args={[0.3, 0.022, 0.12]} />
              {black({ color: '#2a2c31', metalness: 0.7 })}
            </mesh>
            <mesh position={[-0.05, 0.004, 0.09]} rotation-x={0.25}>
              <boxGeometry args={[0.18, 0.012, 0.06]} />
              {black({ color: '#2a2c31' })}
            </mesh>
            {/* Cápsula con el acento de la marca */}
            <mesh position={[0.03, -0.039, 0]} castShadow>
              <boxGeometry args={[0.13, 0.055, 0.085]} />
              <meshStandardMaterial
                color="#7dd3fc"
                emissive="#38bdf8"
                emissiveIntensity={mode === 'playing' ? 0.55 : 0.12}
                roughness={0.4}
              />
            </mesh>
          </group>
        </group>
      </group>
    </group>
  )
}

// --- Escena ------------------------------------------------------------------------------

function CameraRig({ reducedMotion }: { reducedMotion: boolean }) {
  const { camera } = useThree()
  const pointer = useRef({ x: 0, y: 0 })
  const target = useMemo(() => new THREE.Vector3(0.05, -0.55, 0.1), [])

  useEffect(() => {
    const move = (e: PointerEvent) => {
      pointer.current.x = (e.clientX / window.innerWidth) * 2 - 1
      pointer.current.y = (e.clientY / window.innerHeight) * 2 - 1
    }
    window.addEventListener('pointermove', move, { passive: true })
    return () => window.removeEventListener('pointermove', move)
  }, [])

  useFrame((state, dt) => {
    // Encuadre de tres cuartos desde delante a la izquierda: una órbita lentísima (como una
    // cámara de producto) más un paralaje sutil con el ratón.
    const t = reducedMotion ? 0 : state.clock.elapsedTime
    const px = reducedMotion ? 0 : pointer.current.x
    const py = reducedMotion ? 0 : pointer.current.y
    const orbit = Math.sin(t * 0.12) * 0.55
    easing.damp3(
      camera.position,
      [-3.0 + orbit + px * 0.45, 4.3 + Math.sin(t * 0.09) * 0.15 - py * 0.28, 7.7],
      0.7,
      dt,
    )
    camera.lookAt(target)
  })
  return null
}

function Studio() {
  // Entorno procedural: softboxes de estudio, sin descargar ningún HDRI (CSP y sin red).
  return (
    <Environment resolution={256} frames={1}>
      <Lightformer
        form="rect"
        intensity={5}
        position={[0, 6, 0]}
        rotation-x={Math.PI / 2}
        scale={[9, 2.4, 1]}
      />
      <Lightformer
        form="rect"
        intensity={2.4}
        position={[-6, 2.5, 2]}
        rotation-y={Math.PI / 2}
        scale={[7, 1.4, 1]}
      />
      <Lightformer
        form="rect"
        intensity={1.4}
        position={[6, 2, -2]}
        rotation-y={-Math.PI / 2}
        scale={[5, 1, 1]}
      />
      <Lightformer form="rect" intensity={1} position={[0, 2, 8]} scale={[10, 0.6, 1]} />
      <Lightformer form="ring" color="#7dd3fc" intensity={0.8} position={[4, 3.5, 5]} scale={2.5} />
    </Environment>
  )
}

export default function Turntable(props: TurntableProps) {
  const [ready, setReady] = useState(false)
  // Calidad adaptativa: si el equipo no llega a los fotogramas, baja la resolución de
  // render antes que perder fluidez; si va sobrado, la sube.
  const [dpr, setDpr] = useState(() => Math.min(window.devicePixelRatio || 1, 1.5))
  const showRecord = props.mode !== 'idle' || props.bands.length > 0
  return (
    <Canvas
      className={`transition-opacity duration-700 ${ready ? 'opacity-100' : 'opacity-0'}`}
      frameloop={props.frameloop}
      dpr={dpr}
      shadows
      camera={{ fov: 27, position: [-3.0, 4.3, 7.7], near: 0.1, far: 40 }}
      gl={{ antialias: false, alpha: true, powerPreference: 'high-performance' }}
      onCreated={({ gl }) => {
        gl.toneMapping = THREE.AgXToneMapping
        gl.toneMappingExposure = 1.2
        setReady(true)
      }}
      onPointerMissed={() => props.onHover(null, 0, 0)}
      aria-hidden
    >
      <PerformanceMonitor
        bounds={() => [45, 58]}
        // Con la ventana oculta el navegador frena los fotogramas: eso no es falta de potencia.
        onDecline={() => document.hidden || setDpr((d) => Math.max(1, d - 0.25))}
        onIncline={() => setDpr((d) => Math.min(window.devicePixelRatio || 1, 1.75, d + 0.25))}
      />
      <Studio />
      <ambientLight intensity={0.22} />
      <directionalLight
        position={[-2, 7, 4]}
        color="#eef6ff"
        intensity={1.8}
        castShadow
        shadow-mapSize={[1024, 1024]}
        shadow-bias={-0.0004}
        shadow-camera-left={-4}
        shadow-camera-right={4}
        shadow-camera-top={4}
        shadow-camera-bottom={-4}
      />
      {/* Contraluz frío: perfila el canto del chasis y el plato contra el fondo. */}
      <spotLight position={[4, 3, -5]} intensity={16} angle={0.55} penumbra={1} color="#7dd3fc" />
      <spotLight position={[-5, 2.5, -4]} intensity={6} angle={0.6} penumbra={1} color="#bae6fd" />
      <CameraRig reducedMotion={props.reducedMotion} />
      <group scale={0.92}>
        <Plinth />
        <Controls mode={props.mode} />
        <Platter
          mode={props.mode}
          reducedMotion={props.reducedMotion}
          catalog={props.catalog}
          showRecord={showRecord}
        />
        {showRecord && (
          <SetGrooves
            bands={props.bands}
            hovered={props.hovered}
            onHover={props.onHover}
            onSelect={props.onSelect}
            mode={props.mode}
            scannedS={props.scannedS}
            duration={props.duration}
          />
        )}
        <Tonearm
          mode={props.mode}
          scannedS={props.scannedS}
          duration={props.duration}
          reducedMotion={props.reducedMotion}
        />
      </group>
      {/* Suelo de estudio pulido: refleja el plato como en una foto de producto. */}
      <mesh rotation-x={-Math.PI / 2} position={[0, -1.125, 0]}>
        <planeGeometry args={[40, 40]} />
        <MeshReflectorMaterial
          resolution={512}
          blur={[240, 70]}
          mixBlur={1}
          mixStrength={1.6}
          mirror={0.4}
          roughness={1}
          depthScale={1}
          minDepthThreshold={0.4}
          maxDepthThreshold={1.3}
          color="#000000"
          metalness={0.15}
          envMapIntensity={0}
        />
      </mesh>
      {/* La sombra de contacto del chasis no cambia: se calcula una sola vez. */}
      <ContactShadows
        position={[0, -1.12, 0]}
        opacity={0.7}
        scale={10}
        blur={2.4}
        far={1.5}
        frames={1}
        resolution={512}
      />
      <EffectComposer multisampling={2}>
        <Bloom mipmapBlur luminanceThreshold={1} luminanceSmoothing={0.2} intensity={0.8} />
        <Vignette offset={0.35} darkness={0.35} />
      </EffectComposer>
    </Canvas>
  )
}
