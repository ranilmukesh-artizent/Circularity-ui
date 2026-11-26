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

  it('gives every plan-9 pack class a photo that exists, never undefined.webp', () => {
    const known = ['motor', 'pump', 'control', 'powertool', 'it'];
    const classes = ['car_ice', 'car_ev', 'radio', 'baseband', 'router', 'line_card', 'power_unit', 'microwave_link',
      'infusion_pump', 'patient_monitor', 'electric_bed', 'syringe_driver', 'transport_ventilator', 'pulse_oximeter',
      'laptop', 'desktop', 'server', 'network', 'excavator_20t', 'wheel_loader', 'scissor_lift', 'telehandler', 'generator',
      'CMH', 'BRK', 'DCD', 'CRH', 'AGR', 'LSR', 'BAT', 'device', 'phone'];
    for (const c of classes) expect(known, c).toContain(photoFile(c));
  });

  it('falls back to a generic photo for an unknown, empty or missing class', () => {
    for (const c of ['zeppelin', '', undefined, null]) {
      expect(photoSrc(c as string)).not.toContain('undefined');
      expect(photoSrc(c as string)).toMatch(/^assets\/products\/[a-z]+\.webp$/);
    }
  });

  it('uses one placeholder per pack: vehicles, network kit and medical devices differ', () => {
    expect(new Set([photoFile('car_ice'), photoFile('radio'), photoFile('infusion_pump')]).size).toBe(3);
    expect(photoFile('car_ev')).toBe(photoFile('car_ice'));
  });
});
