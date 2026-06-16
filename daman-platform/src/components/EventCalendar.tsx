import React, { useState, useEffect } from 'react';
import { Calendar, Clock, TrendingUp, AlertCircle, RefreshCw } from 'lucide-react';
import { supabase } from '../lib/supabase';

interface EconomicEvent {
  id: string;
  event_title: string;
  country: string;
  event_date: string;
  impact: 'high' | 'medium' | 'low';
  forecast?: string;
  previous?: string;
  actual?: string;
  currency?: string;
}

interface GroupedEvents {
  [date: string]: EconomicEvent[];
}

export default function EventCalendar() {
  const [events, setEvents] = useState<EconomicEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    fetchEvents();
  }, []);

  const fetchEvents = async () => {
    try {
      setRefreshing(true);

      // Call edge function to fetch and update events
      const { data: functionData, error: functionError } = await supabase.functions.invoke('fetch-economic-events');

      if (functionError) {
        console.error('Error calling function:', functionError);
      }

      // Fetch from database - Only US events
      const today = new Date();
      const fiveDaysLater = new Date();
      fiveDaysLater.setDate(today.getDate() + 7);

      const { data, error } = await supabase
        .from('economic_events')
        .select('*')
        .gte('event_date', today.toISOString())
        .lte('event_date', fiveDaysLater.toISOString())
        .in('impact', ['high', 'medium'])
        .eq('country', 'USD')
        .order('event_date', { ascending: true });

      if (error) {
        console.error('Error fetching events:', error);
      } else {
        setEvents(data || []);
      }
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const convertToDubaiTime = (dateStr: string): { date: string; time: string } => {
    const date = new Date(dateStr);

    // Convert to Dubai time (UTC+4)
    const dubaiTime = new Date(date.toLocaleString('en-US', { timeZone: 'Asia/Dubai' }));

    const formattedDate = dubaiTime.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });

    const formattedTime = dubaiTime.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });

    return { date: formattedDate, time: formattedTime };
  };

  const groupEventsByDate = (events: EconomicEvent[]): GroupedEvents => {
    const grouped: GroupedEvents = {};

    events.forEach(event => {
      const { date } = convertToDubaiTime(event.event_date);
      if (!grouped[date]) {
        grouped[date] = [];
      }
      grouped[date].push(event);
    });

    return grouped;
  };

  const getImpactColor = (impact: string) => {
    switch (impact) {
      case 'high':
        return 'bg-red-500';
      case 'medium':
        return 'bg-orange-500';
      default:
        return 'bg-yellow-500';
    }
  };

  const getImpactBadgeColor = (impact: string) => {
    switch (impact) {
      case 'high':
        return 'bg-red-100 text-red-800';
      case 'medium':
        return 'bg-orange-100 text-orange-800';
      default:
        return 'bg-yellow-100 text-yellow-800';
    }
  };

  const getCurrencyFlag = (country: string) => {
    const flags: { [key: string]: string } = {
      'USD': '🇺🇸',
      'EUR': '🇪🇺',
      'GBP': '🇬🇧',
      'JPY': '🇯🇵',
      'CHF': '🇨🇭',
      'AUD': '🇦🇺',
      'CAD': '🇨🇦',
      'NZD': '🇳🇿',
    };
    return flags[country] || '🌐';
  };

  const groupedEvents = groupEventsByDate(events);
  const businessDays = Object.keys(groupedEvents);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-100 rounded-lg">
            <Calendar className="w-6 h-6 text-blue-600" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-gray-900">US Economic Event Calendar</h2>
            <p className="text-sm text-gray-500">Next 5 business days - US High & Medium impact events (Dubai Time)</p>
          </div>
        </div>
        <button
          onClick={fetchEvents}
          disabled={refreshing}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-6 p-4 bg-gray-50 rounded-lg">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500"></div>
          <span className="text-sm text-gray-700">High Impact</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-orange-500"></div>
          <span className="text-sm text-gray-700">Medium Impact</span>
        </div>
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-gray-500" />
          <span className="text-sm text-gray-700">Times shown in Dubai Time (UTC+4)</span>
        </div>
      </div>

      {events.length === 0 ? (
        <div className="text-center py-12 bg-gray-50 rounded-lg">
          <AlertCircle className="w-12 h-12 text-gray-400 mx-auto mb-3" />
          <p className="text-gray-600">No economic events scheduled for the next 5 business days</p>
          <button
            onClick={fetchEvents}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Load Events
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          {businessDays.map((date, idx) => (
            <div key={idx} className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
              {/* Date Header */}
              <div className="bg-gradient-to-r from-blue-600 to-blue-700 px-6 py-3">
                <h3 className="text-lg font-semibold text-white">{date}</h3>
              </div>

              {/* Events List */}
              <div className="divide-y divide-gray-100">
                {groupedEvents[date].map((event, eventIdx) => {
                  const { time } = convertToDubaiTime(event.event_date);

                  return (
                    <div
                      key={eventIdx}
                      className="p-4 hover:bg-gray-50 transition-colors"
                    >
                      <div className="flex items-start gap-4">
                        {/* Impact Indicator */}
                        <div className="flex-shrink-0 pt-1">
                          <div className={`w-3 h-3 rounded-full ${getImpactColor(event.impact)}`}></div>
                        </div>

                        {/* Event Details */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between gap-4 mb-2">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-2xl">{getCurrencyFlag(event.country)}</span>
                                <span className="font-semibold text-gray-900">{event.event_title}</span>
                              </div>
                              <div className="flex items-center gap-3 text-sm text-gray-600">
                                <div className="flex items-center gap-1">
                                  <Clock className="w-4 h-4" />
                                  <span className="font-medium">{time}</span>
                                </div>
                                <span className="text-gray-400">|</span>
                                <span className={`px-2 py-1 rounded-full text-xs font-medium ${getImpactBadgeColor(event.impact)}`}>
                                  {event.impact.toUpperCase()}
                                </span>
                                <span className="text-gray-400">|</span>
                                <span className="font-medium">{event.currency || event.country}</span>
                              </div>
                            </div>
                          </div>

                          {/* Forecast & Previous */}
                          {(event.forecast || event.previous) && (
                            <div className="flex items-center gap-4 mt-2 p-3 bg-gray-50 rounded-lg">
                              {event.forecast && (
                                <div className="flex items-center gap-2">
                                  <TrendingUp className="w-4 h-4 text-blue-600" />
                                  <div>
                                    <div className="text-xs text-gray-500">Forecast</div>
                                    <div className="text-sm font-semibold text-gray-900">{event.forecast}</div>
                                  </div>
                                </div>
                              )}
                              {event.previous && (
                                <div className="flex items-center gap-2">
                                  <div>
                                    <div className="text-xs text-gray-500">Previous</div>
                                    <div className="text-sm font-medium text-gray-700">{event.previous}</div>
                                  </div>
                                </div>
                              )}
                              {event.actual && (
                                <div className="flex items-center gap-2">
                                  <div>
                                    <div className="text-xs text-gray-500">Actual</div>
                                    <div className="text-sm font-bold text-green-600">{event.actual}</div>
                                  </div>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Info Footer */}
      <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-blue-900">
            <p className="font-semibold mb-1">About Economic Events</p>
            <p className="text-blue-700">
              High impact events can cause significant market volatility. Medium impact events may also affect market movements.
              All times are displayed in Dubai Time (UTC+4). Plan your trades accordingly.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
