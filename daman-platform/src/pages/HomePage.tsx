import { useState } from 'react';
import { Globe, Shield, TrendingUp, BarChart3, Zap, Lock } from 'lucide-react';
import NewsTicker from '../components/NewsTicker';
import MarketMoversTicker from '../components/MarketMoversTicker';
import FeatureModal from '../components/FeatureModal';
import { featureDetails, FeatureDetail } from '../data/featureDetails';

interface HomePageProps {
  onNavigate: (page: string) => void;
}

export default function HomePage({ onNavigate }: HomePageProps) {
  const [selectedFeature, setSelectedFeature] = useState<FeatureDetail | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleFeatureClick = (featureTitle: string) => {
    const detail = featureDetails[featureTitle];
    if (detail) {
      setSelectedFeature(detail);
      setIsModalOpen(true);
    }
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setTimeout(() => setSelectedFeature(null), 300);
  };

  const features = [
    {
      icon: Globe,
      title: 'Global Market Access',
      description: 'Trade in US markets plus 23+ international countries with seamless execution',
    },
    {
      icon: BarChart3,
      title: 'Multi-Asset Trading',
      description: 'Access equities, options, and futures all from a single platform',
    },
    {
      icon: Zap,
      title: 'Real-Time Data',
      description: 'Live market data, instant execution, and up-to-the-second analytics',
    },
    {
      icon: Shield,
      title: 'Secure & Regulated',
      description: 'SEC regulated with bank-level security and data encryption',
    },
    {
      icon: TrendingUp,
      title: 'Advanced Analytics',
      description: 'Professional-grade charts, indicators, and market insights',
    },
    {
      icon: Lock,
      title: 'Protected Accounts',
      description: 'SIPC insured accounts with multi-factor authentication',
    },
  ];

  return (
    <div className="w-full">
      <NewsTicker />
      <MarketMoversTicker />

      <section className="py-20 bg-gradient-to-b from-slate-50 via-slate-100 to-slate-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold text-slate-900 mb-4">
              Everything You Need to Trade Successfully
            </h2>
            <p className="text-xl text-slate-600 max-w-3xl mx-auto">
              Professional trading tools, real-time data, and comprehensive market coverage designed for serious traders.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {features.map((feature, index) => {
              const Icon = feature.icon;
              return (
                <button
                  key={index}
                  onClick={() => handleFeatureClick(feature.title)}
                  className="bg-white rounded-xl p-8 hover:shadow-xl transition-all hover:-translate-y-1 border border-slate-200 hover:border-daman-blue-300 text-left cursor-pointer group focus:outline-none focus:ring-2 focus:ring-daman-blue-500 focus:ring-offset-2"
                >
                  <div className="bg-daman-blue-100 w-14 h-14 rounded-lg flex items-center justify-center mb-6 group-hover:bg-daman-blue-200 transition-colors">
                    <Icon className="h-7 w-7 text-daman-blue-600" />
                  </div>
                  <h3 className="text-xl font-semibold text-slate-900 mb-3 group-hover:text-daman-blue-700 transition-colors">
                    {feature.title}
                  </h3>
                  <p className="text-slate-700 leading-relaxed mb-4">{feature.description}</p>
                  <div className="text-daman-blue-600 font-medium text-sm flex items-center">
                    Learn more
                    <svg className="w-4 h-4 ml-1 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </section>

      <section className="py-20 bg-slate-900 text-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
            <div>
              <h2 className="text-4xl font-bold mb-6">
                Trade with Confidence Across Global Markets
              </h2>
              <p className="text-xl text-slate-300 mb-8 leading-relaxed">
                DAMAN Securities provides access to major stock exchanges worldwide, from NYSE and NASDAQ to international markets across Europe, Asia, and beyond.
              </p>
              <ul className="space-y-4">
                <li className="flex items-start">
                  <div className="bg-daman-blue-600 rounded-full p-1 mr-3 mt-1">
                    <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <div>
                    <span className="font-semibold text-lg">US Markets: </span>
                    <span className="text-slate-300">NYSE, NASDAQ, AMEX with extended hours trading</span>
                  </div>
                </li>
                <li className="flex items-start">
                  <div className="bg-daman-blue-600 rounded-full p-1 mr-3 mt-1">
                    <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <div>
                    <span className="font-semibold text-lg">Options Trading: </span>
                    <span className="text-slate-300">Advanced strategies with real-time Greeks and analytics</span>
                  </div>
                </li>
                <li className="flex items-start">
                  <div className="bg-daman-blue-600 rounded-full p-1 mr-3 mt-1">
                    <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <div>
                    <span className="font-semibold text-lg">Futures: </span>
                    <span className="text-slate-300">Commodities, indices, and currency futures</span>
                  </div>
                </li>
              </ul>
            </div>

            <div className="bg-slate-800 rounded-2xl p-8 border border-slate-700">
              <h3 className="text-2xl font-bold mb-6 text-daman-blue-300">Market Coverage</h3>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-slate-900 rounded-lg p-4 border border-slate-700">
                  <div className="text-3xl font-bold text-white mb-1">24+</div>
                  <div className="text-slate-400 text-sm">Countries</div>
                </div>
                <div className="bg-slate-900 rounded-lg p-4 border border-slate-700">
                  <div className="text-3xl font-bold text-white mb-1">150+</div>
                  <div className="text-slate-400 text-sm">Global Exchanges</div>
                </div>
                <div className="bg-slate-900 rounded-lg p-4 border border-slate-700">
                  <div className="text-3xl font-bold text-white mb-1">50K+</div>
                  <div className="text-slate-400 text-sm">Tradable Securities</div>
                </div>
                <div className="bg-slate-900 rounded-lg p-4 border border-slate-700">
                  <div className="text-3xl font-bold text-white mb-1">24/5</div>
                  <div className="text-slate-400 text-sm">Trading Access</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="py-20 bg-gradient-to-br from-daman-blue-600 to-daman-blue-700 text-white">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="text-4xl font-bold mb-6">Ready to Start Trading?</h2>
          <p className="text-xl text-white opacity-95 mb-8">
            Join thousands of traders who trust DAMAN Securities for their investment needs.
          </p>
          <a
            href="https://www.clientam.com/sso/Login?partnerID=ds2020"
            target="_blank"
            rel="noopener noreferrer"
            className="bg-white text-daman-blue-700 px-10 py-4 rounded-lg font-semibold text-lg hover:bg-slate-100 transition-all shadow-xl transform hover:scale-105 inline-block"
          >
            Open Your Account Today
          </a>
        </div>
      </section>

      <FeatureModal
        isOpen={isModalOpen}
        onClose={closeModal}
        feature={selectedFeature}
      />
    </div>
  );
}
