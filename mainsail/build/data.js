// All site copy lives here. Edit text in this file, then run `node mainsail/build/build.js`.
'use strict';

const site = {
  name: 'Mainsail Consulting Group',
  shortName: 'Mainsail',
  legalName: 'By Main Sail Consulting Group',
  tagline: 'Precision-Driven Project Management',
  email: 'info@bymainsail.com',
  url: 'https://www.bymainsail.com',
  description: 'Mainsail Consulting Group specializes in project leadership and risk management for large-scale construction projects, focusing on the hospital, medical services, pharmaceutical, and higher education sectors.',
  // Optional: set a form endpoint (e.g. a Formspree or Basin URL) to receive
  // submissions server-side. Leave empty to fall back to the visitor's mail client.
  formEndpoint: '',
};

const services = [
  {
    slug: 'owners-project-management',
    n: '01',
    title: "Owners Project Management",
    short: 'Mainsail manages your project from start to finish, covering design, budgeting, permitting, construction oversight, and final handover. Our proactive approach ensures efficiency, cost control, and quality at every stage.',
    img: 'opm',
    intro: 'Our construction project management consulting company offers comprehensive project management services tailored to meet the unique needs of each client.',
    body: [
      'We provide expert guidance throughout the project lifecycle, from initial planning and budgeting to execution and completion. Our team specializes in risk management, contract administration, and quality control, ensuring that projects are delivered on time and within budget.',
      'With a focus on collaboration and communication, we work closely with stakeholders to optimize resources and streamline processes, helping you achieve your project goals efficiently and effectively. Let us help you turn your vision into reality with our dedicated project management offerings.',
    ],
    capabilities: [
      { title: 'Risk Management', text: 'Our risk management services for construction project management provide comprehensive strategies to identify, assess, and mitigate potential risks throughout the project lifecycle. We ensure that projects are completed on time and within budget while minimizing disruptions and enhancing safety.' },
      { title: 'Contract Administration', text: 'Contract administration involves managing and overseeing all aspects of contracts throughout the life of a construction project. We offer comprehensive services, including contract negotiation, compliance monitoring, risk management, and ensuring that all parties meet their contractual obligations. We provide expertise in facilitating communication between stakeholders and resolving disputes, ensuring that projects run smoothly and efficiently from start to finish.' },
      { title: 'Budget Control', text: 'Mainsail meticulously oversees all budget items to ensure projects remain on track and within budget. We prioritize cost control, eliminating any creeping costs, and maintaining transparency throughout the entire process to deliver successful outcomes for our clients.' },
    ],
  },
  {
    slug: 'construction-mitigation',
    n: '02',
    title: 'Construction Mitigation',
    short: 'As a full-service firm, we offer end-to-end project management, coordinating all stakeholders, mitigating risks, and ensuring timely, cost-effective completion. We provide real-time updates for complete transparency.',
    img: 'mitigation',
    intro: 'Our commitment to community impact: construction projects often extend beyond the immediate worksite, affecting neighboring departments, buildings, and entire communities.',
    body: [
      "Our clients are frequently positioned in densely populated or sensitive areas where any disruption could interfere with day-to-day operations. That's why we take a proactive, community-focused approach to every project we undertake.",
      "We deeply understand the importance of minimizing disruptions and preserving the functionality of surrounding environments. By engaging with local stakeholders, understanding their concerns, and maintaining open lines of communication, we ensure that the needs of our clients and their neighbors are aligned. Whether it's coordinating with adjacent departments, mitigating noise, or carefully planning construction schedules, our goal is to reduce any adverse impact on surrounding communities.",
      'Through close collaboration with contractors, we ensure that construction timelines are adhered to with efficiency, while always keeping the community in mind. We pride ourselves on being more than just project managers: we serve as advocates for our clients and their neighbors, balancing progress with responsibility.',
      "As the voice for project stakeholders, we take ownership of not just the project but also the relationships and responsibilities that come with working in a shared environment. This ensures that every project is delivered on time and on budget without compromising the integrity of the surrounding area. Mainsail Consulting Group is committed to protecting our clients' interests and fostering positive, lasting relationships with the communities we serve.",
    ],
    capabilities: [],
  },
  {
    slug: 'building-infrastructure-assessment',
    n: '03',
    title: 'Building Infrastructure Assessment',
    short: "Mainsail's Mechanical Engineers optimize building systems and drive sustainability by collaborating with A/E firms to achieve net-zero energy goals. They ensure efficiency throughout the project lifecycle, from design development to reviewing contract drawings and submittals.",
    img: 'infrastructure',
    intro: 'At Mainsail Consulting Group, our Mechanical Engineers are a vital component of the turnkey solutions we offer to our clients.',
    body: [
      "We're committed to helping clients fully understand and optimize their building systems. As the focus on sustainability grows, particularly in reducing greenhouse gas emissions, our engineers work closely with A/E firms to enhance the efficiency of building operations and strive toward net-zero energy goals.",
      'Our mechanical engineers play a pivotal role throughout the project lifecycle. From the early stages of design development to the review of contract drawings and project submittals, they ensure that all systems are designed and executed to the highest standards of efficiency and sustainability. Whether reviewing technical specifications or advising on system optimization, our team is dedicated to creating smarter, more sustainable buildings for the future.',
    ],
    capabilities: [],
  },
  {
    slug: 'relocation-management',
    n: '04',
    title: 'Relocation Management',
    short: 'Mainsail provides seamless, turn-key management for relocating occupants into newly prepared spaces upon project completion. From planning to move-in, we handle every detail to minimize downtime, ensuring each new space is ready for immediate use and a smooth transition for all involved.',
    img: 'relocation',
    intro: 'Upon the successful completion of each project, the transition into a new space can be a complex and challenging process.',
    body: [
      'Mainsail Consulting Group is committed to providing seamless, turn-key project management services to ensure the smooth relocation of occupants and their belongings into newly prepared spaces.',
      "We meticulously manage every aspect of the relocation process, from planning and coordination to the final move-in. Whether it's a small office or a large-scale facility, we approach every relocation with the same dedication and precision. Our goal is to minimize downtime and disruption while ensuring that the new space is ready for immediate use.",
      'No matter the size or complexity of the project, Mainsail Consulting Group maintains its unwavering commitment to excellence, ensuring a stress-free transition for all stakeholders.',
    ],
    capabilities: [],
  },
  {
    slug: 'adjunct-staffing',
    n: '05',
    title: 'Adjunct Staffing',
    short: 'Mainsail offers on-demand project management and professional services to support clients during critical phases or resource gaps. This flexible approach allows clients to efficiently scale support, ensuring high-quality and timely project outcomes.',
    img: 'staffing',
    intro: 'Our mission is clear: to offer our clients peace of mind.',
    body: [
      'We strive to be the driving force behind your projects, enabling you to concentrate on your overarching vision while we handle the intricacies of planning, execution, and delivery.',
      'With a network of preferred suppliers at our disposal, we ensure that any staffing gaps and resource needs are seamlessly bridged for our customers.',
    ],
    capabilities: [],
  },
];

const sectors = [
  { n: '01', title: 'Hospital', img: 'hospital' },
  { n: '02', title: 'Medical Services', img: 'medical' },
  { n: '03', title: 'Pharmaceutical', img: 'pharma' },
  { n: '04', title: 'Higher Education', img: 'education' },
];

const pillars = [
  { n: '01', title: 'Proven Expertise', text: "With decades of experience managing complex projects across various sectors, Mainsail Consulting Group brings a depth of knowledge and reliability you can trust. Our team's attention to detail and commitment to excellence ensures your project is in capable hands every step of the way." },
  { n: '02', title: 'Transparent Communication', text: "We believe trust is built on transparency. At Mainsail, we keep you informed with real-time updates and clear communication, ensuring you're always in the loop and confident in our progress. Our open and honest approach fosters a partnership based on trust and collaboration." },
  { n: '03', title: 'Commitment to Your Vision and Budget', text: 'Your goals are our priority. We align our efforts with your mission, handling the complexities of project management while ensuring your vision is brought to life. With Mainsail, you can trust that we are dedicated to achieving the best possible outcomes for you and your stakeholders.' },
];

const home = {
  heroEyebrow: 'Experienced Professionals',
  heroTitle: ['Precision-driven', 'project', 'management.'],
  heroText: site.description,
  heroStat: { value: 130, label: 'Trusted with the oversight of 130 sites.' },
  introTitle: 'A dedicated partner, aligned to your mission.',
  introText: [
    'Mainsail Consulting Group brings a tailored, hands-on approach to project management. We work as a dedicated partner, aligning our efforts with your mission to ensure project success. Our values of transparency, efficiency, and trust guide every decision we make, ensuring that we not only meet but exceed your expectations.',
    'We are committed to delivering exceptional client solutions through our expertise in owner project management and professional services. Our approach goes beyond merely meeting deadlines and budgets; we prioritize building trust and ensuring that every detail is meticulously addressed to achieve outstanding project outcomes.',
  ],
  servicesTitle: 'Five disciplines, one standard.',
  servicesText: 'Our experienced team specializes in guiding complex projects from inception to completion, allowing our clients to focus on their broader vision while we navigate the intricacies of execution. From life sciences to large-scale facilities, we provide turnkey solutions that exceed expectations, all with a focus on transparency, efficiency, and client satisfaction.',
  statementTitle: 'Leave the stress with us.',
  statementCta: 'Get a quote',
  sectorsTitle: 'Complexity is our default.',
  approachTitle: 'Built on trust.',
  contactTitle: 'Tell us about your project.',
};

module.exports = { site, services, sectors, pillars, home };
