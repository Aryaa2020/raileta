const aliases = {
  MAS: 'chennai madras chennai central', SBC: 'bengaluru bangalore blr ksr majestic',
  BNC: 'bengaluru bangalore blr cantonment cantt', BNCE: 'bengaluru bangalore blr east',
  KJM: 'kr puram krishnarajapuram', KPD: 'katpadi', JTJ: 'jolarpettai',
};
const normalize = value => String(value || '').toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, ' ').trim();
const tokensMatch = (query, text) => normalize(query).split(/\s+/).every(token => token.length <= 3 ? text.split(/\s+/).some(word => word.startsWith(token)) : text.includes(token));
const stationText = stop => normalize(`${stop.station_code} ${stop.station_name} ${aliases[stop.station_code] || ''}`);

export function matchingTrains(trains, query) {
  if (!query.trim()) return [];
  const route = query.trim().split(/\s+to\s+|\s*→\s*|\s*->\s*|\s*–\s*|\s*-\s*/i);
  return trains.filter(train => {
    const stops = train.stops || [];
    if (normalize(query) === normalize(train.train_name) || normalize(query) === normalize(`${train.train_number} ${train.train_name}`)) return true;
    if (route.length === 2 && route.every(part => normalize(part))) {
      return stops.some((stop, i) => tokensMatch(route[0], stationText(stop)) &&
        stops.slice(i + 1).some(target => tokensMatch(route[1], stationText(target))));
    }
    return tokensMatch(query, normalize(`${train.train_number} ${train.train_name} ${stops.map(stationText).join(' ')} ${train.current_station || ''}`));
  }).sort((a, b) => Number(String(b.train_number) === query.trim()) - Number(String(a.train_number) === query.trim()));
}

export function routeLabel(train) {
  return train.stops?.length ? `${train.stops[0].station_name} → ${train.stops.at(-1).station_name}` : 'Open available train report';
}
