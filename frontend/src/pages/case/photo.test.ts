import { describe, expect, it } from 'vitest';
import { photoFile, photoSrc } from './photo';

describe('UI audit gap 8: the product photo of any class', () => {
  it('keeps the industrial classes on their own photos', () => {
    expect(photoSrc('motor')).toBe('assets/products/motor.webp');
    expect(photoSrc('pump')).toBe('assets/products/pump.webp');
    expect(photoSrc('control')).toBe('assets/products/control.webp');
    expect(photoSrc('drill')).toBe('assets/products/powertool.webp');
    expect(photoSrc('batch')).toBe('assets/products/powertool.webp');
    expect(photoSrc('it')).toBe('assets/products/it.webp');
  });

  it('keeps the tool fleet on the power-tool photo', () => {
    for (const c of ['CMH', 'BRK', 'DCD', 'CRH', 'AGR', 'LSR', 'BAT']) expect(photoSrc(c), c).toBe('assets/products/powertool.webp');
  });

  it('gives no photo to a pack class: it shows its tile, never an industrial photo or undefined.webp', () => {
    const classes = ['car_ice', 'car_ev', 'radio', 'baseband', 'router', 'line_card', 'power_unit', 'microwave_link',
      'infusion_pump', 'patient_monitor', 'electric_bed', 'syringe_driver', 'transport_ventilator', 'pulse_oximeter',
      'laptop', 'desktop', 'server', 'network', 'phone', 'device', 'ev_pack', 'industrial_pack', 'alternator', 'starter',
      'transmission', 'excavator_20t', 'wheel_loader', 'scissor_lift', 'telehandler', 'generator'];
    for (const c of classes) { expect(photoSrc(c), c).toBeNull(); expect(photoFile(c), c).toBeNull(); }
  });

  it('gives no photo to an unknown, empty or missing class', () => {
    for (const c of ['zeppelin', '', undefined, null, 'toString', '__proto__']) expect(photoSrc(c as string)).toBeNull();
  });
});
