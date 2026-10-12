import React from "react";

// Original illustration: a béton-brut civic building with deep sunbreakers, a curved
// parasol roof and Le Corbusier-style enamel panels, under the Shivalik hills at dusk,
// reflected in a pool. Inspired by Chandigarh's Capitol Complex, not a copy of any building.
const COLS = 9;
const ROWS = 4;
const CELL_W = 74;
const CELL_H = 86;
const X0 = 470;
const Y0 = 420;
// which sunbreaker recesses carry a coloured panel: [col, row, colour]
const PAINTED = [
  [1, 0, "var(--c-red)"],
  [6, 1, "var(--c-ochre)"],
  [3, 2, "var(--c-cobalt)"],
  [8, 3, "var(--c-green)"],
  [5, 3, "var(--c-red)"],
];

export default function Facade() {
  const cells = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const x = X0 + c * CELL_W;
      const y = Y0 + r * CELL_H;
      const paint = PAINTED.find(([pc, pr]) => pc === c && pr === r);
      cells.push(
        <g key={`${r}-${c}`}>
          {/* recess */}
          <rect x={x + 8} y={y + 8} width={CELL_W - 16} height={CELL_H - 14} fill={paint ? paint[2] : "#3d4146"} />
          {/* shadow cast by the fin and the slab above: this is what makes the depth */}
          <path d={`M${x + 8} ${y + 8} h${CELL_W - 16} v18 L${x + 26} ${y + CELL_H - 6} h-18 z`} fill="#000" opacity={paint ? 0.28 : 0.42} />
          {/* slab and fins */}
          <rect x={x} y={y} width={CELL_W} height="8" fill="url(#concrete-lit)" />
          <rect x={x} y={y} width="8" height={CELL_H} fill="url(#concrete-lit)" />
        </g>
      );
    }
  }

  return (
    <svg className="facade" viewBox="0 0 1200 900" preserveAspectRatio="xMaxYMid slice" role="img"
      aria-label="Illustration of a concrete civic building with coloured panels under the Shivalik hills at dusk">
      <defs>
        <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#c9d2d9" />
          <stop offset="0.55" stopColor="#e7d8bf" />
          <stop offset="1" stopColor="#f0c98f" />
        </linearGradient>
        <radialGradient id="sunglow" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#f6c25a" stopOpacity="0.85" />
          <stop offset="1" stopColor="#f6c25a" stopOpacity="0" />
        </radialGradient>
        <pattern id="concrete-lit" patternUnits="userSpaceOnUse" width="256" height="256">
          <image href="/concrete.png" width="256" height="256" />
        </pattern>
        <pattern id="concrete-shade" patternUnits="userSpaceOnUse" width="256" height="256">
          <image href="/concrete-dark.png" width="256" height="256" />
        </pattern>
        <linearGradient id="pool" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#5f6d79" />
          <stop offset="1" stopColor="#2c343b" />
        </linearGradient>
        <linearGradient id="fade" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="var(--paper)" stopOpacity="1" />
          <stop offset="0.38" stopColor="var(--paper)" stopOpacity="0.85" />
          <stop offset="0.62" stopColor="var(--paper)" stopOpacity="0" />
        </linearGradient>
        <clipPath id="reflect-clip">
          <rect x="0" y="770" width="1200" height="130" />
        </clipPath>
      </defs>

      {/* sky, sun, hills */}
      <rect width="1200" height="900" fill="url(#sky)" />
      <circle cx="905" cy="215" r="190" fill="url(#sunglow)" />
      <circle cx="905" cy="215" r="66" fill="var(--c-ochre)" />
      <path d="M0 360 L120 300 L210 330 L330 250 L430 305 L560 230 L700 300 L820 240 L960 310 L1080 260 L1200 300 V500 H0 Z" fill="#9aa5ae" />
      <path d="M0 410 L150 350 L260 385 L400 320 L520 370 L640 330 L780 380 L900 335 L1040 375 L1200 345 V520 H0 Z" fill="#7d8992" />

      {/* the name over the city: Devanagari set into the sky, cut off by the roofline */}
      <text x="1170" y="372" textAnchor="end" className="sky-word" lang="hi">
        पात्रता
      </text>

      {/* hyperbolic tower behind the block */}
      <path d="M560 420 C 585 360, 585 300, 560 250 L 660 250 C 635 300, 635 360, 660 420 Z" fill="url(#concrete-lit)" />
      <path d="M560 420 C 585 360, 585 300, 560 250 L 585 250 C 600 300, 600 360, 590 420 Z" fill="#000" opacity="0.18" />
      <ellipse cx="610" cy="250" rx="50" ry="7" fill="#b9b4ab" />

      {/* parasol roof on pilotis */}
      <path d="M400 330 Q 780 395 1200 318 L 1200 352 Q 780 430 400 362 Z" fill="url(#concrete-lit)" />
      <path d="M400 362 Q 780 430 1200 352 L 1200 366 Q 780 446 400 374 Z" fill="#000" opacity="0.25" />
      {[470, 640, 810, 980, 1150].map((x) => (
        <rect key={x} x={x - 5} y={372} width="10" height="52" fill="url(#concrete-shade)" />
      ))}

      {/* main block with sunbreakers */}
      <rect x={X0 - 14} y={Y0 - 10} width={COLS * CELL_W + 30} height={ROWS * CELL_H + 22} fill="url(#concrete-lit)" />
      {cells}
      <rect x={X0 - 14} y={Y0 + ROWS * CELL_H + 4} width={COLS * CELL_W + 30} height="10" fill="#000" opacity="0.2" />

      {/* ground and pool with reflection */}
      <rect x="0" y="770" width="1200" height="130" fill="url(#pool)" />
      <g clipPath="url(#reflect-clip)" opacity="0.32" transform="translate(0 1540) scale(1 -1)">
        <rect x={X0 - 14} y={Y0 - 10} width={COLS * CELL_W + 30} height={ROWS * CELL_H + 22} fill="#cfcac0" />
        {PAINTED.map(([c, r, col]) => (
          <rect key={`${c}${r}`} x={X0 + c * CELL_W + 8} y={Y0 + r * CELL_H + 8} width={CELL_W - 16} height={CELL_H - 14} fill={col} />
        ))}
      </g>
      {[790, 812, 838, 866].map((y, i) => (
        <rect key={y} x={480 + i * 40} y={y} width={520 - i * 70} height="2" fill="#fff" opacity="0.12" />
      ))}
      <rect x="0" y="766" width="1200" height="6" fill="#b3ada2" />

      {/* left fade so text stays legible */}
      <rect className="facade-fade" width="1200" height="900" fill="url(#fade)" />
    </svg>
  );
}
