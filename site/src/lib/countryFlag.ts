/** Map FastF1 / Jolpica country labels to ISO 3166-1 alpha-2 for flag emoji. */
const COUNTRY_ISO: Record<string, string> = {
  Argentina: 'AR',
  Australia: 'AU',
  Austria: 'AT',
  Azerbaijan: 'AZ',
  Bahrain: 'BH',
  Belgium: 'BE',
  Brazil: 'BR',
  Canada: 'CA',
  China: 'CN',
  France: 'FR',
  Germany: 'DE',
  Hungary: 'HU',
  India: 'IN',
  Italy: 'IT',
  Japan: 'JP',
  Korea: 'KR',
  Malaysia: 'MY',
  Mexico: 'MX',
  Monaco: 'MC',
  Netherlands: 'NL',
  Portugal: 'PT',
  Qatar: 'QA',
  Russia: 'RU',
  Singapore: 'SG',
  Spain: 'ES',
  Turkey: 'TR',
  'South Africa': 'ZA',
  'Saudi Arabia': 'SA',
  USA: 'US',
  'United States': 'US',
  UK: 'GB',
  'United Kingdom': 'GB',
  'Great Britain': 'GB',
  UAE: 'AE',
  'United Arab Emirates': 'AE',
  'Abu Dhabi': 'AE',
}

function isoToFlagEmoji(iso: string): string {
  if (iso.length !== 2) return ''
  const code = iso.toUpperCase()
  return String.fromCodePoint(
    ...[...code].map((c) => 0x1f1e6 - 65 + c.charCodeAt(0)),
  )
}

/** Flag emoji for a race country label, or empty string if unknown. */
export function countryFlag(country: string | null | undefined): string {
  if (!country) return ''
  const iso = COUNTRY_ISO[country.trim()]
  return iso ? isoToFlagEmoji(iso) : ''
}
