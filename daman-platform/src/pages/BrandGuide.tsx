import { Palette, Type, LayoutGrid as Layout, Check } from 'lucide-react';
import LogoShowcase from '../components/LogoShowcase';
import DamanLogo from '../components/DamanLogo';

export default function BrandGuide() {
  const colorPalette = [
    { name: 'Primary Blue', hex: '#1969C3', usage: 'Primary actions, CTAs, accents' },
    { name: 'Blue Dark', hex: '#14539C', usage: 'Hover states, emphasis' },
    { name: 'Blue Light', hex: '#4787CF', usage: 'Backgrounds, subtle accents' },
    { name: 'Navy Blue', hex: '#043572', usage: 'Headers, hero sections' },
    { name: 'Slate Dark', hex: '#0F172A', usage: 'Primary text, dark backgrounds' },
    { name: 'Slate Medium', hex: '#334155', usage: 'Body text, secondary content' },
    { name: 'Slate Light', hex: '#F1F5F9', usage: 'Backgrounds, cards' },
    { name: 'White', hex: '#FFFFFF', usage: 'Canvas, cards, overlays' },
    { name: 'Red Accent', hex: '#DC2626', usage: 'Losses, alerts, negative data' },
  ];

  const typography = [
    {
      name: 'Primary Font',
      font: 'Inter, system-ui, sans-serif',
      usage: 'All body text, UI elements',
      weights: ['Regular (400)', 'Medium (500)', 'Semibold (600)', 'Bold (700)']
    },
  ];

  const logoVariations = [
    {
      name: 'Primary Horizontal Logo',
      description: 'Full logo with icon and text side-by-side',
      usage: 'Main navigation, headers, official documents',
      minWidth: '180px'
    },
    {
      name: 'Stacked Logo',
      description: 'Icon above text in vertical arrangement',
      usage: 'Mobile navigation, square spaces, social media',
      minWidth: '120px'
    },
    {
      name: 'Icon Only',
      description: 'TrendingUp icon in emerald',
      usage: 'Favicons, app icons, tight spaces',
      minWidth: '32px'
    },
    {
      name: 'Wordmark',
      description: 'Text only without icon',
      usage: 'Secondary placements, footers',
      minWidth: '140px'
    },
  ];

  return (
    <div className="min-h-screen bg-slate-50 py-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-12">
          <h1 className="text-4xl font-bold text-slate-900 mb-4">DAMAN Securities Brand Guide</h1>
          <p className="text-xl text-slate-600">Complete visual identity system and design specifications</p>
        </div>

        <section className="mb-16">
          <div className="flex items-center space-x-3 mb-8">
            <DamanLogo size="sm" />
            <h2 className="text-3xl font-bold text-slate-900">Logo Variations</h2>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-12">
            <div className="bg-white rounded-xl shadow-md border border-slate-200 p-8">
              <h3 className="text-lg font-bold text-slate-900 mb-6">Primary Horizontal Logo</h3>
              <div className="bg-slate-900 rounded-lg p-12 flex items-center justify-center mb-6">
                <DamanLogo size="lg" className="text-white" />
              </div>
              <div className="space-y-2 text-sm">
                <p><strong>Usage:</strong> Main navigation, headers, official documents</p>
                <p><strong>Minimum Width:</strong> 200px</p>
                <p><strong>Clear Space:</strong> 16px on all sides</p>
              </div>
            </div>

            <div className="bg-white rounded-xl shadow-md border border-slate-200 p-8">
              <h3 className="text-lg font-bold text-slate-900 mb-6">Icon Only</h3>
              <div className="bg-slate-900 rounded-lg p-12 flex items-center justify-center mb-6">
                <DamanLogo size="lg" />
              </div>
              <div className="space-y-2 text-sm">
                <p><strong>Usage:</strong> Favicons, app icons, tight spaces</p>
                <p><strong>Minimum Size:</strong> 40px × 40px</p>
                <p><strong>Clear Space:</strong> 8px on all sides</p>
              </div>
            </div>

            <div className="bg-white rounded-xl shadow-md border border-slate-200 p-8">
              <h3 className="text-lg font-bold text-slate-900 mb-6">Light Background</h3>
              <div className="bg-white border-2 border-slate-200 rounded-lg p-12 flex items-center justify-center mb-6">
                <DamanLogo size="lg" />
              </div>
              <div className="space-y-2 text-sm">
                <p><strong>Usage:</strong> White backgrounds, light surfaces</p>
                <p><strong>Colors:</strong> Navy blue (#003A70) and purple (#682145)</p>
              </div>
            </div>

            <div className="bg-white rounded-xl shadow-md border border-slate-200 p-8">
              <h3 className="text-lg font-bold text-slate-900 mb-6">Wordmark</h3>
              <div className="bg-slate-900 rounded-lg p-12 flex items-center justify-center mb-6">
                <span className="text-4xl font-bold text-white">DAMAN Securities</span>
              </div>
              <div className="space-y-2 text-sm">
                <p><strong>Usage:</strong> Secondary placements, text-only contexts</p>
                <p><strong>Minimum Width:</strong> 160px</p>
                <p><strong>Clear Space:</strong> 12px on all sides</p>
              </div>
            </div>
          </div>

          <div className="mb-12">
            <h3 className="text-2xl font-bold text-slate-900 mb-6">All Logo Variations</h3>
            <LogoShowcase />
          </div>

          <div className="bg-gradient-to-br from-daman-navy to-daman-blue-700 rounded-xl p-8 text-white">
            <h3 className="text-xl font-bold mb-4">Logo Design Rationale</h3>
            <div className="space-y-3 text-daman-blue-100">
              <p><strong>Icon Choice:</strong> The TrendingUp arrow symbolizes growth, success, and upward market momentum - core to trading.</p>
              <p><strong>Typography:</strong> Bold, confident font conveys professionalism and trustworthiness in financial services.</p>
              <p><strong>Color:</strong> Professional blue palette inspired by Daman Securities - represents trust, stability, and financial expertise while maintaining a modern, tech-forward aesthetic.</p>
              <p><strong>Simplicity:</strong> Clean, scalable design works across all mediums from mobile apps to billboards.</p>
            </div>
          </div>
        </section>

        <section className="mb-16">
          <div className="flex items-center space-x-3 mb-8">
            <Palette className="h-8 w-8 text-daman-blue-600" />
            <h2 className="text-3xl font-bold text-slate-900">Color Palette</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {colorPalette.map((color, index) => (
              <div key={index} className="bg-white rounded-xl shadow-md border border-slate-200 overflow-hidden">
                <div
                  className="h-32 w-full"
                  style={{ backgroundColor: color.hex }}
                ></div>
                <div className="p-6">
                  <h3 className="font-bold text-slate-900 mb-2">{color.name}</h3>
                  <p className="text-2xl font-mono text-slate-700 mb-3">{color.hex}</p>
                  <p className="text-sm text-slate-600">{color.usage}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-8 bg-white rounded-xl shadow-md border border-slate-200 p-8">
            <h3 className="text-xl font-bold text-slate-900 mb-4">Color Usage Guidelines</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h4 className="font-semibold text-slate-900 mb-3 flex items-center">
                  <Check className="h-5 w-5 text-daman-blue-600 mr-2" />
                  Do
                </h4>
                <ul className="space-y-2 text-slate-700">
                  <li>• Use blue for positive growth, CTAs, and primary actions</li>
                  <li>• Maintain sufficient contrast ratios (4.5:1 minimum)</li>
                  <li>• Use slate colors for hierarchy and depth</li>
                  <li>• Apply white space generously</li>
                </ul>
              </div>
              <div>
                <h4 className="font-semibold text-slate-900 mb-3 flex items-center">
                  <span className="h-5 w-5 flex items-center justify-center text-red-600 mr-2 font-bold">×</span>
                  Don't
                </h4>
                <ul className="space-y-2 text-slate-700">
                  <li>• Don't use blue for negative data or losses</li>
                  <li>• Avoid low contrast color combinations</li>
                  <li>• Don't introduce additional brand colors</li>
                  <li>• Never use pure black (#000000)</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section className="mb-16">
          <div className="flex items-center space-x-3 mb-8">
            <Type className="h-8 w-8 text-daman-blue-600" />
            <h2 className="text-3xl font-bold text-slate-900">Typography</h2>
          </div>

          <div className="bg-white rounded-xl shadow-md border border-slate-200 p-8 mb-8">
            <h3 className="text-xl font-bold text-slate-900 mb-6">Type Scale</h3>
            <div className="space-y-6">
              <div className="border-b border-slate-200 pb-6">
                <p className="text-sm text-slate-600 mb-2">Heading 1 - 36px / 2.25rem - Bold</p>
                <h1 className="text-4xl font-bold text-slate-900">The quick brown fox jumps</h1>
              </div>
              <div className="border-b border-slate-200 pb-6">
                <p className="text-sm text-slate-600 mb-2">Heading 2 - 30px / 1.875rem - Bold</p>
                <h2 className="text-3xl font-bold text-slate-900">The quick brown fox jumps</h2>
              </div>
              <div className="border-b border-slate-200 pb-6">
                <p className="text-sm text-slate-600 mb-2">Heading 3 - 24px / 1.5rem - Bold</p>
                <h3 className="text-2xl font-bold text-slate-900">The quick brown fox jumps</h3>
              </div>
              <div className="border-b border-slate-200 pb-6">
                <p className="text-sm text-slate-600 mb-2">Body Large - 20px / 1.25rem - Regular</p>
                <p className="text-xl text-slate-700">The quick brown fox jumps over the lazy dog</p>
              </div>
              <div className="border-b border-slate-200 pb-6">
                <p className="text-sm text-slate-600 mb-2">Body - 16px / 1rem - Regular</p>
                <p className="text-base text-slate-700">The quick brown fox jumps over the lazy dog</p>
              </div>
              <div>
                <p className="text-sm text-slate-600 mb-2">Small - 14px / 0.875rem - Regular</p>
                <p className="text-sm text-slate-700">The quick brown fox jumps over the lazy dog</p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-md border border-slate-200 p-8">
            <h3 className="text-xl font-bold text-slate-900 mb-4">Font Weights</h3>
            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-slate-50 rounded-lg">
                <span className="font-normal text-slate-900">Regular - 400</span>
                <span className="text-slate-600">Body text, paragraphs</span>
              </div>
              <div className="flex items-center justify-between p-4 bg-slate-50 rounded-lg">
                <span className="font-medium text-slate-900">Medium - 500</span>
                <span className="text-slate-600">Emphasis, labels</span>
              </div>
              <div className="flex items-center justify-between p-4 bg-slate-50 rounded-lg">
                <span className="font-semibold text-slate-900">Semibold - 600</span>
                <span className="text-slate-600">Buttons, navigation</span>
              </div>
              <div className="flex items-center justify-between p-4 bg-slate-50 rounded-lg">
                <span className="font-bold text-slate-900">Bold - 700</span>
                <span className="text-slate-600">Headings, emphasis</span>
              </div>
            </div>
          </div>
        </section>

        <section className="mb-16">
          <div className="flex items-center space-x-3 mb-8">
            <Layout className="h-8 w-8 text-daman-blue-600" />
            <h2 className="text-3xl font-bold text-slate-900">Layout & Spacing</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="bg-white rounded-xl shadow-md border border-slate-200 p-8">
              <h3 className="text-xl font-bold text-slate-900 mb-6">Spacing System</h3>
              <div className="space-y-4">
                <div className="flex items-center space-x-4">
                  <div className="w-16 text-sm text-slate-600">4px</div>
                  <div className="h-4 bg-daman-blue-600 rounded" style={{ width: '16px' }}></div>
                </div>
                <div className="flex items-center space-x-4">
                  <div className="w-16 text-sm text-slate-600">8px</div>
                  <div className="h-4 bg-daman-blue-600 rounded" style={{ width: '32px' }}></div>
                </div>
                <div className="flex items-center space-x-4">
                  <div className="w-16 text-sm text-slate-600">12px</div>
                  <div className="h-4 bg-daman-blue-600 rounded" style={{ width: '48px' }}></div>
                </div>
                <div className="flex items-center space-x-4">
                  <div className="w-16 text-sm text-slate-600">16px</div>
                  <div className="h-4 bg-daman-blue-600 rounded" style={{ width: '64px' }}></div>
                </div>
                <div className="flex items-center space-x-4">
                  <div className="w-16 text-sm text-slate-600">24px</div>
                  <div className="h-4 bg-daman-blue-600 rounded" style={{ width: '96px' }}></div>
                </div>
                <div className="flex items-center space-x-4">
                  <div className="w-16 text-sm text-slate-600">32px</div>
                  <div className="h-4 bg-daman-blue-600 rounded" style={{ width: '128px' }}></div>
                </div>
                <div className="flex items-center space-x-4">
                  <div className="w-16 text-sm text-slate-600">48px</div>
                  <div className="h-4 bg-daman-blue-600 rounded" style={{ width: '192px' }}></div>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-xl shadow-md border border-slate-200 p-8">
              <h3 className="text-xl font-bold text-slate-900 mb-6">Border Radius</h3>
              <div className="space-y-6">
                <div>
                  <p className="text-sm text-slate-600 mb-2">Small - 4px</p>
                  <div className="h-16 bg-daman-blue-100 rounded"></div>
                </div>
                <div>
                  <p className="text-sm text-slate-600 mb-2">Medium - 8px</p>
                  <div className="h-16 bg-daman-blue-100 rounded-lg"></div>
                </div>
                <div>
                  <p className="text-sm text-slate-600 mb-2">Large - 12px</p>
                  <div className="h-16 bg-daman-blue-100 rounded-xl"></div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section>
          <div className="bg-gradient-to-br from-daman-navy to-daman-blue-800 rounded-xl p-12 text-white text-center">
            <h2 className="text-3xl font-bold mb-4">Brand Mission</h2>
            <p className="text-xl text-daman-blue-100 max-w-3xl mx-auto leading-relaxed">
              DAMAN Securities empowers traders worldwide with professional-grade tools, real-time market intelligence,
              and secure access to global financial markets. We believe in transparency, innovation, and putting our
              clients' success first.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
