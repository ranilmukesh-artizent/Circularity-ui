/** The detail tabs of each stage (stData's tabs), in the demo's order, with its keys and labels. */
import type { ReactNode } from 'react';
import type { CaseAnalysis, CaseRec, CaseScreen } from '../../../api/case';
import * as D from './DecideTabs';
import { ComplianceTab, DeviceTab, QuoteTab } from './DeviceTabs';
import * as E from './EarlyTabs';
import * as X from './ExecuteTabs';

export interface TabProps { c: CaseRec; a: CaseAnalysis; s: CaseScreen }
export type TabDef = [key: string, label: string, View: (p: TabProps) => ReactNode];

export function stageTabs(c: CaseRec, n: number): TabDef[] {
  const r = c.chosen || c.recommendation;
  switch (n) {
    case 1: return [['lease', 'Lease record', E.LeaseTab], ['customer', 'Customer', E.CustomerTab], ['systems', 'Systems', E.SystemsTab]];
    case 2: return [['auth', 'Authorisation', E.AuthTab], ['finance', 'Finance', E.FinanceTab]];
    case 3: return [['route', 'Route', E.LaneTab], ['cost', 'Cost trace', E.LaneCostTab]];
    case 4: return [['evidence', 'Evidence checklist', E.EvidenceListTab], ['location', 'Location', E.LocationTab], ['holding', 'Holding cost', E.HoldingTab]];
    case 5: {
      const early: TabDef[] = [['findings', 'Findings', E.FindingsTab], ['diag', 'Diagnostic condition', E.DiagTab], ['cert', 'Certified period', E.CertTab], ['photos', 'Photos', E.PhotosTab]];
      // a received device starts with its Device tab (P9-6.4), then the Quote tab when it has one (P9-6.5)
      const extra: TabDef[] = c.device
        ? [
            ['device', 'Device', DeviceTab],
            ...(c.device.quoteCheck ? [['quote', 'Quote', QuoteTab] as TabDef] : []),
            ...(c.device.registry ? [['compliance', 'Compliance', ComplianceTab] as TabDef] : []), // the registry check (P9-6.6)
          ]
        : [];
      return [...extra, ...early];
    }
    case 6: return [
      ['packet', 'Decision packet', D.PacketTab], ['compare', 'Compare outcomes', D.CompareTab], ['why', 'Why this outcome', D.WhyTab],
      ['evidence', 'Evidence', D.EvidenceTab], ['whatif', 'What-if and edge cases', D.WhatIfTab], ['predicted', 'How it was predicted', D.PredictedTab],
      ['demand', 'Demand', D.DemandTab],
    ];
    case 7: return r ? [['rationale', 'Rationale', X.RationaleTab], ['checks', 'Checks', X.ChecksTab], ['history', 'History', X.HistoryTab]] : [];
    case 8: return r ? [['plan', 'Plan', X.PlanTab], ['route', 'Route and timing', X.MoveTab], ['acks', 'Messages and acknowledgements', X.AcksTab], ['instr', 'Instruction', X.InstrTab]] : [];
    case 9: return r ? [['delivery', 'Delivery', X.DeliveryTab], ['costs', 'Actual costs', X.CostsTab], ['docs', 'Documents', X.DocsTab]] : [];
    default: return r ? [['lines', 'Lines', X.LinesTab], ['learn', 'Learning record', X.LearnTab], ['carried', 'Carried forward', X.CarriedTab]] : [];
  }
}
