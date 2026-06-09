// ISO 3166-1 alpha-3 → numeric, to match world-atlas topojson feature ids.
// Covers the major mineral-producing countries (extend as needed).
export const ISO3_TO_NUM: Record<string, string> = {
  AFG: "004", AGO: "024", ARE: "784", ARG: "032", AUS: "036", AUT: "040",
  AZE: "031", BEL: "056", BFA: "854", BGR: "100", BOL: "068", BRA: "076",
  BWA: "072", CAN: "124", CHE: "756", CHL: "152", CHN: "156", CIV: "384",
  CMR: "120", COD: "180", COG: "178", COL: "170", CUB: "192", CZE: "203",
  DEU: "276", DOM: "214", DZA: "012", ECU: "218", EGY: "818", ERI: "232",
  ESP: "724", ETH: "231", FIN: "246", FRA: "250", GAB: "266", GBR: "826",
  GEO: "268", GHA: "288", GIN: "324", GRC: "300", GTM: "320", GUY: "328",
  IDN: "360", IND: "356", IRN: "364", ITA: "380", JPN: "392", KAZ: "398",
  KEN: "404", KGZ: "417", KOR: "410", LAO: "418", LBR: "430", LBY: "434",
  MAR: "504", MDG: "450", MEX: "484", MLI: "466", MMR: "104", MNG: "496",
  MOZ: "508", MRT: "478", MWI: "454", MYS: "458", NAM: "516", NCL: "540",
  NER: "562", NGA: "566", NOR: "578", NZL: "554", PAK: "586", PER: "604",
  PHL: "608", PNG: "598", POL: "616", PRT: "620", ROU: "642", RUS: "643",
  RWA: "646", SAU: "682", SDN: "729", SEN: "686", SLE: "694", SRB: "688",
  SUR: "740", SWE: "752", TGO: "768", THA: "764", TJK: "762", TUN: "788",
  TUR: "792", TZA: "834", UGA: "800", UKR: "804", USA: "840", UZB: "860",
  VEN: "862", VNM: "704", ZAF: "710", ZMB: "894", ZWE: "716",
}
